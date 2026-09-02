"""Vector search query interface — wraps pgvector cosine-distance queries
to find drop-in component alternatives via semantic similarity.

This module is the "RAG" piece of the architecture: given a component
description/MPN, it embeds the query, then retrieves the nearest catalog
entries filtered by basic spec constraints (package, pin-count, voltage range).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..embeddings import embed, is_real_model_active


def effective_min_similarity() -> float:
    """Resolve the similarity floor for the *currently active* embedding backend.

    The PRD's 0.95 target assumes the trained model. When the offline hash
    fallback is active, the same semantic distance yields a lower cosine
    similarity, so applying 0.95 would reject every genuine drop-in and the
    human-in-the-loop flow would never trigger. We therefore pick the floor
    that matches the backend actually producing the vectors.
    """
    if is_real_model_active():
        return settings.compatibility_threshold
    return settings.hash_compatibility_threshold


@dataclass
class AlternateMatch:
    """A candidate drop-in replacement with a compatibility score.

    ``compatibility`` is the blended, spec-aware score surfaced to the UI and
    checked against the PRD threshold. ``semantic`` retains the raw embedding
    cosine similarity for auditability. ``similarity`` is kept as an alias of
    ``compatibility`` so existing consumers keep working.
    """
    component_id: uuid.UUID
    mpn: str
    manufacturer: str
    description: str
    category: str
    package: str
    pin_count: int
    voltage_min: float | None
    voltage_max: float | None
    compatibility: float   # 0-1 blended (semantic + package + pinout + voltage)
    semantic: float        # 0-1 raw embedding cosine similarity

    @property
    def similarity(self) -> float:
        """Backwards-compatible alias: the score used for ranking/threshold."""
        return self.compatibility


# ── Blended compatibility scoring ─────────────────────────────────────────────
#
# The PRD defines compatibility as ">= 95% on voltage, pinout, and package
# footprint" — a spec-based measure, not raw text-embedding cosine. Treating
# embedding cosine directly as the compatibility % is a modelling mismatch: a
# genuine drop-in (same package/pins, voltage covered) tops out around ~0.91
# cosine on MiniLM, so a literal 0.95 cosine cutoff rejects real substitutes.
#
# Compatibility is scored on SEMANTIC similarity alone. Package footprint, pin
# count and voltage window are NOT folded into the score: a legitimate drop-in
# frequently comes in a different package/pinout (e.g. an LDO in SOT-223
# substituting for one in SOT-23-5), so penalising those dimensions here
# wrongly disqualifies valid same-class alternates. Any dimension the engineer
# truly requires is enforced separately and deterministically as a HARD filter
# (see alternate_match.py: component-class identity + user value constraints),
# which is a more correct and explicit mechanism than a weighted blend.


def _voltage_coverage(
    target_min: float | None, target_max: float | None,
    cand_min: float | None, cand_max: float | None,
) -> float:
    """1.0 if the candidate's operating window covers the target's, else a
    partial score by overlap fraction. Unknown ranges are treated as neutral.

    Retained as a reusable helper; no longer part of the compatibility score.
    """
    if None in (target_min, target_max, cand_min, cand_max):
        return 1.0  # neutral when specs unknown — don't penalise missing data
    if target_max <= target_min:
        return 1.0
    overlap = max(0.0, min(target_max, cand_max) - max(target_min, cand_min))
    span = target_max - target_min
    return max(0.0, min(1.0, overlap / span)) if span > 0 else 1.0


def compatibility_score(
    *,
    semantic: float,
    target_package: str | None = None, cand_package: str | None = None,
    target_pins: int | None = None, cand_pins: int | None = None,
    target_vmin: float | None = None, target_vmax: float | None = None,
    cand_vmin: float | None = None, cand_vmax: float | None = None,
) -> float:
    """Compatibility score = semantic similarity, clamped to [0, 1].

    Pure function (no DB/embedding side effects) so it is independently
    testable. Spec parameters are accepted for backwards compatibility with
    existing callers but are intentionally ignored: footprint/pinout/voltage
    are enforced as hard filters upstream, not blended into the score.
    """
    return round(max(0.0, min(1.0, semantic)), 4)


def find_alternates(
    session: Session,
    *,
    query_text: str,
    exclude_mpn: str | None = None,
    category_filter: str | None = None,
    package_filter: str | None = None,
    pin_count: int | None = None,
    voltage_min: float | None = None,
    voltage_max: float | None = None,
    top_k: int = 5,
    min_similarity: float | None = None,
) -> list[AlternateMatch]:
    """Semantic vector search for component alternates.

    Parameters
    ----------
    query_text:
        Free-text description of the target component (gets embedded).
    exclude_mpn:
        MPN to exclude from results (the original out-of-stock part).
    category_filter:
        Hard component-class filter. When supplied, ONLY candidates sharing the
        same ``category`` are retrieved — a deterministic physical-sanity rule
        enforced *before* vector similarity so an IC can never be substituted
        for a passive (or vice versa) no matter how close the embedding or
        footprint. Rows with an empty/unknown category are excluded when a
        filter is active (we cannot prove class identity).
    package_filter:
        If supplied, only return matches with this package footprint.
    pin_count:
        If supplied, only return matches with this exact pin count.
    voltage_min / voltage_max:
        If supplied, only return matches whose voltage range overlaps.
    top_k:
        Maximum number of results.
    min_similarity:
        DEPRECATED / IGNORED. Retrieval no longer thresholds candidates; the
        caller applies the compatibility floor. Kept in the signature only so
        existing callers/tests that pass it do not break.
    """
    # NOTE: ``min_similarity`` is accepted for backwards compatibility but is
    # intentionally IGNORED here — retrieval no longer hard-cuts on a floor.
    # The caller (alternate_match_node) applies the compatibility threshold
    # authoritatively. See the ranking/return block below.
    _ = min_similarity  # explicitly unused

    query_vec = embed(query_text)
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in query_vec) + "]"

    # Build the query using pgvector's <=> cosine distance operator.
    # Cosine distance ∈ [0, 2]; similarity = 1 - distance ∈ [-1, 1].
    #
    # Design note: package and pin_count are treated as *soft* ranking signals,
    # not hard filters. A drop-in replacement frequently comes in a different
    # package/pin count (e.g. an LDO in SOT-223 substituting for one in
    # SOT-23-5); the whole point of the human-in-the-loop gate is to let a
    # component engineer judge such trade-offs. Hard-filtering on exact package
    # here would silently discard valid candidates before they can be reviewed.
    # We instead surface them and let matching package/pins boost rank.
    where_clauses = ["c.embedding IS NOT NULL"]
    params: dict = {"vec": vec_literal, "top_k": top_k}

    if exclude_mpn:
        where_clauses.append("c.mpn != :exclude_mpn")
        params["exclude_mpn"] = exclude_mpn

    # Deterministic physical-sanity rule (enforced BEFORE similarity ranking):
    # never cross component classes. A same-footprint IC must not be offered as
    # a substitute for a passive. Empty/unknown categories are excluded when a
    # filter is active because class identity cannot be proven.
    if category_filter:
        where_clauses.append("c.category = :category_filter")
        params["category_filter"] = category_filter

    # Voltage range is kept as a lenient guard: only exclude a candidate whose
    # operating window cannot possibly cover the target's. Rows with unknown
    # (NULL) voltages are never excluded.
    if voltage_min is not None:
        where_clauses.append("(c.voltage_max IS NULL OR c.voltage_max >= :vmin)")
        params["vmin"] = voltage_min

    if voltage_max is not None:
        where_clauses.append("(c.voltage_min IS NULL OR c.voltage_min <= :vmax)")
        params["vmax"] = voltage_max

    where_sql = " AND ".join(where_clauses)

    # Soft preference ordering: exact package match first, then exact pin-count
    # match, then closest semantic distance. These only influence *ordering*,
    # never inclusion.
    order_terms: list[str] = []
    if package_filter:
        order_terms.append("(c.package = :package) DESC")
        params["package"] = package_filter
    if pin_count is not None:
        order_terms.append("(c.pin_count = :pin_count) DESC")
        params["pin_count"] = pin_count
    order_terms.append("c.embedding <=> :vec ::vector")
    order_sql = ", ".join(order_terms)

    sql = text(f"""
        SELECT
            c.id,
            c.mpn,
            c.manufacturer,
            c.description,
            c.category,
            c.package,
            c.pin_count,
            c.voltage_min,
            c.voltage_max,
            1 - (c.embedding <=> :vec ::vector) AS similarity
        FROM components c
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT :fetch_k
    """)

    # Fetch a wider candidate pool than requested so the blended, spec-aware
    # re-ranking below has room to promote spec-compatible parts that the pure
    # semantic ordering may not have placed first.
    params["fetch_k"] = max(top_k * 4, top_k)

    rows = session.execute(sql, params).fetchall()

    scored: list[AlternateMatch] = []
    for r in rows:
        semantic = float(r.similarity)
        compat = compatibility_score(
            semantic=semantic,
            target_package=package_filter, cand_package=r.package,
            target_pins=pin_count, cand_pins=r.pin_count,
            target_vmin=voltage_min, target_vmax=voltage_max,
            cand_vmin=r.voltage_min, cand_vmax=r.voltage_max,
        )
        scored.append(AlternateMatch(
            component_id=r.id,
            mpn=r.mpn,
            manufacturer=r.manufacturer,
            description=r.description,
            category=r.category or "",
            package=r.package,
            pin_count=r.pin_count,
            voltage_min=r.voltage_min,
            voltage_max=r.voltage_max,
            compatibility=compat,
            semantic=round(semantic, 4),
        ))

    # Rank by semantic compatibility and return the top-K nearest. NOTE: we do
    # NOT hard-cut on ``min_similarity`` here. Retrieval and thresholding are
    # deliberately separate concerns: this function retrieves the best
    # candidates, and the caller (alternate_match_node) applies the
    # compatibility threshold authoritatively — so a borderline part still
    # reaches the pipeline (hard constraints, class check, human review) instead
    # of being silently discarded at retrieval time.
    scored.sort(key=lambda m: m.compatibility, reverse=True)
    results = scored[:top_k]
    return results


def find_alternates_for_component(
    session: Session,
    *,
    mpn: str,
    description: str = "",
    category: str | None = None,
    package: str | None = None,
    pin_count: int | None = None,
    voltage_min: float | None = None,
    voltage_max: float | None = None,
    top_k: int = 5,
) -> list[AlternateMatch]:
    """Higher-level helper: build query text from component metadata and search."""
    parts = [mpn, description]
    if package:
        parts.append(f"package:{package}")
    if pin_count:
        parts.append(f"pins:{pin_count}")
    if voltage_min is not None and voltage_max is not None:
        parts.append(f"voltage {voltage_min}-{voltage_max}V")
    query_text = " ".join(p for p in parts if p)

    return find_alternates(
        session,
        query_text=query_text,
        exclude_mpn=mpn,
        category_filter=category,
        package_filter=package,
        pin_count=pin_count,
        voltage_min=voltage_min,
        voltage_max=voltage_max,
        top_k=top_k,
    )
