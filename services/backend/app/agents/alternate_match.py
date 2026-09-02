"""Agent 3 — Alternate Match (Vector RAG + Dynamic User Constraints):
Enforces dynamic user-selected critical parameters as strict SQL filters 
before pgvector similarity scoring and batch stock verification."""
from __future__ import annotations

from typing import Dict, List, Set, Any
from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import Component, SupplierStock
from ..db.session import SessionLocal
from .events import emit
from .state import WorkflowState
from ..docai.vector_search import (
    compatibility_score,
    effective_min_similarity,
    find_alternates_for_component,
)

# ---------------------------------------------------------------------------
# Dynamic Parameter Mapping Registry
#
# Maps each user-selectable constraint *dimension* to the Component column(s)
# and comparison used to build a hard SQL filter. Only dimensions backed by
# real, populated columns are exposed — offering a constraint that silently
# no-ops (because the column doesn't exist) would be misleading.
#
# Semantics are "must match the original part": for a given out-of-stock line
# item, the constraint value is taken from that item's ORIGINAL component, so
# the policy applies coherently across a multi-line BOM. The API/UI therefore
# send a *set of dimension names* (not fixed values); values are resolved per
# line item in ``resolve_constraints_for_original``.
#
#   package       -> candidate.package == original.package        (exact footprint)
#   pin_count     -> candidate.pin_count == original.pin_count     (exact pinout)
#   manufacturer  -> candidate.manufacturer == original.manufacturer
#   voltage       -> candidate voltage window must COVER original's
#                    (voltage_min <= orig.voltage_min AND voltage_max >= orig.voltage_max)
# ---------------------------------------------------------------------------
COLUMN_MAPPING: Dict[str, Any] = {
    "package": {"col": Component.package, "op": "eq"},
    "pin_count": {"col": Component.pin_count, "op": "eq"},
    "manufacturer": {"col": Component.manufacturer, "op": "eq"},
    # Range attributes: alternate window must cover the original's window.
    "voltage_min": {"col": Component.voltage_min, "op": "lte"},
    "voltage_max": {"col": Component.voltage_max, "op": "gte"},
}

# Dimension names the UI/API may request. "voltage" expands to the voltage_min
# + voltage_max coverage pair. Shared with the API layer for validation.
ALLOWED_CONSTRAINTS: Set[str] = {"package", "pin_count", "manufacturer", "voltage"}

# ---------------------------------------------------------------------------
# Value-based threshold registry
#
# Maps each UI-selectable parameter *key* to the candidate component attribute
# and comparison operator used to enforce a user-supplied VALUE (as opposed to
# the "must match original" mode above). This is what powers value-based
# thresholds: the engineer types a target (e.g. voltage_max = 3.3) and every
# candidate is filtered against that concrete bound.
#
#   op semantics (candidate attribute `cand` vs. user `value`):
#     eq  -> cand == value            (exact: package, pin_count, manufacturer)
#     min -> cand >= value            (candidate must meet at least this floor)
#     max -> cand <= value            (candidate must not exceed this ceiling)
#
# `attr` is the AlternateMatch/Component field checked. Keys whose data only
# lives in the JSONB `specs` column use `spec_key` and are matched best-effort.
# ---------------------------------------------------------------------------
VALUE_CONSTRAINT_SPECS: Dict[str, Dict[str, Any]] = {
    "package": {"attr": "package", "op": "eq", "cast": "str"},
    "pin_count": {"attr": "pin_count", "op": "eq", "cast": "int"},
    "manufacturer": {"attr": "manufacturer", "op": "eq", "cast": "str"},
    "voltage_max": {"attr": "voltage_max", "op": "max", "cast": "float"},
    "voltage_min": {"attr": "voltage_min", "op": "min", "cast": "float"},
    # Spec-backed (best-effort) numeric thresholds.
    "frequency_max": {"spec_key": "frequency_max", "op": "max", "cast": "float"},
    "temp_max": {"spec_key": "temp_max", "op": "max", "cast": "float"},
    "resistance": {"spec_key": "resistance", "op": "eq", "cast": "float"},
    "capacitance": {"spec_key": "capacitance", "op": "eq", "cast": "float"},
    "mounting_type": {"spec_key": "mounting_type", "op": "eq", "cast": "str"},
}

# Keys the value-based API accepts (superset of ALLOWED_CONSTRAINTS names).
ALLOWED_VALUE_CONSTRAINTS: Set[str] = set(VALUE_CONSTRAINT_SPECS.keys())


def _coerce(value: Any, cast: str) -> Any:
    """Best-effort coercion of a user-supplied constraint value."""
    if value is None:
        return None
    try:
        if cast == "int":
            return int(float(value))
        if cast == "float":
            return float(value)
        return str(value).strip()
    except (TypeError, ValueError):
        return None


def normalize_value_constraints(raw: Any) -> Dict[str, Any]:
    """Normalise a user-supplied value-constraints map into
    ``{key: coerced_value}`` restricted to ``ALLOWED_VALUE_CONSTRAINTS``.

    Accepts either ``{key: value}`` or ``{key: {"value": v}}``. Unknown keys
    and un-coercible / empty values are dropped.
    """
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, val in raw.items():
        if key not in VALUE_CONSTRAINT_SPECS:
            continue
        if isinstance(val, dict):
            val = val.get("value")
        coerced = _coerce(val, VALUE_CONSTRAINT_SPECS[key]["cast"])
        if coerced is None or (isinstance(coerced, str) and not coerced):
            continue
        out[key] = coerced
    return out


def _passes_value_constraints(match: Any, value_constraints: Dict[str, Any]) -> bool:
    """True if a candidate satisfies every user-supplied value threshold.

    For spec-backed keys, reads from the candidate's ``specs`` JSONB when the
    attribute isn't a first-class column. A missing candidate value fails the
    constraint (we cannot prove compliance).
    """
    for key, value in value_constraints.items():
        spec = VALUE_CONSTRAINT_SPECS.get(key)
        if not spec:
            continue
        op = spec["op"]
        if "attr" in spec:
            cand = getattr(match, spec["attr"], None)
        else:
            # Spec-backed key: only enforceable if the candidate exposes a
            # `specs` mapping. Candidates (AlternateMatch) don't currently carry
            # one, so skip rather than reject every candidate outright.
            specs = getattr(match, "specs", None)
            if not isinstance(specs, dict):
                continue
            cand = specs.get(spec["spec_key"])
        cand = _coerce(cand, spec["cast"])
        if cand is None:
            return False
        if op == "eq":
            # Case-insensitive compare for strings.
            if isinstance(cand, str) and isinstance(value, str):
                if cand.strip().lower() != value.strip().lower():
                    return False
            elif cand != value:
                return False
        elif op == "min" and not (cand >= value):
            return False
        elif op == "max" and not (cand <= value):
            return False
    return True


# Fraction by which range (min/max) constraints are widened in the elastic
# tolerance fallback. Exact constraints (eq) are never relaxed.
RELAX_FRACTION = 0.10

# Multi-tier elastic tolerance schedule. Each entry is the fraction by which
# range (min/max) bounds are widened *relative to the user's original value*
# (fractions are NOT compounded — each tier re-derives from the original).
# Tiers are attempted in order only while the previous pass returned zero
# candidates. After the widest tier, a final "drop range constraints" tier is
# attempted (keeping exact/footprint constraints strict).
RELAX_TIERS: tuple[float, ...] = (0.10, 0.25, 0.50)


def drop_range_constraints(
    value_constraints: Dict[str, Any]
) -> tuple[Dict[str, Any], list[dict]]:
    """Final fallback tier: remove all numeric *range* (min/max) constraints,
    keeping exact-match constraints (package, pin_count, manufacturer, ...)
    strict. Returns ``(remaining_map, dropped)`` where ``dropped`` lists the
    range parameters that were removed, for the ``constraints_relaxed`` event.
    """
    remaining: Dict[str, Any] = {}
    dropped: list[dict] = []
    for key, value in value_constraints.items():
        spec = VALUE_CONSTRAINT_SPECS.get(key)
        if spec and spec["op"] in ("min", "max") and isinstance(value, (int, float)):
            dropped.append({"parameter": key, "op": spec["op"], "from": value, "dropped": True})
        else:
            remaining[key] = value
    return remaining, dropped


def relax_value_constraints(
    value_constraints: Dict[str, Any], fraction: float = RELAX_FRACTION
) -> tuple[Dict[str, Any], list[dict]]:
    """Produce a relaxed copy of value constraints for a fallback tier.

    Only numeric *range* constraints (ops ``min``/``max``) are widened by
    ``fraction``; exact-match constraints (``eq`` — package, pin_count,
    manufacturer, mounting_type) are kept strict so footprint/identity is never
    compromised. Widening is always computed from the ORIGINAL value, so tiers
    do not compound.

      • ``max`` (candidate must be <= value)  → raise ceiling: value * (1 + f)
      • ``min`` (candidate must be >= value)  → lower floor:  value * (1 - f)

    Returns ``(relaxed_map, changes)`` where ``changes`` describes each widened
    bound for the ``constraints_relaxed`` event. If nothing is relaxable the
    map is returned unchanged with an empty ``changes`` list.
    """
    relaxed: Dict[str, Any] = dict(value_constraints)
    changes: list[dict] = []
    pct = round(fraction * 100)

    for key, value in value_constraints.items():
        spec = VALUE_CONSTRAINT_SPECS.get(key)
        if not spec or spec["op"] not in ("min", "max"):
            continue
        if not isinstance(value, (int, float)):
            continue
        if spec["op"] == "max":
            new_value = round(value * (1 + fraction), 6)
        else:  # min
            new_value = round(value * (1 - fraction), 6)
        relaxed[key] = new_value
        changes.append({
            "parameter": key,
            "op": spec["op"],
            "from": value,
            "to": new_value,
            "widened_by_pct": pct,
        })

    return relaxed, changes


def resolve_constraints_for_original(
    requested: Any, original: Component | None
) -> Dict[str, Any]:
    """Turn the user's set of non-negotiable dimension names into concrete
    ``{column_key: value}`` filters using the ORIGINAL component's specs.

    ``requested`` may be a list/set of dimension names (preferred) or a dict
    (dimension -> truthy) for backwards compatibility. Returns an empty dict
    when nothing resolvable is requested or the original is unknown.
    """
    if not requested or original is None:
        return {}

    # Normalise to a set of enabled dimension names.
    if isinstance(requested, dict):
        names = {k for k, v in requested.items() if v}
    else:
        names = set(requested)

    resolved: Dict[str, Any] = {}
    if "package" in names and original.package:
        resolved["package"] = original.package
    if "pin_count" in names and original.pin_count:
        resolved["pin_count"] = original.pin_count
    if "manufacturer" in names and original.manufacturer:
        resolved["manufacturer"] = original.manufacturer
    if "voltage" in names:
        # Alternate must cover the original's operating window.
        if original.voltage_min is not None:
            resolved["voltage_min"] = original.voltage_min
        if original.voltage_max is not None:
            resolved["voltage_max"] = original.voltage_max
    return resolved


def _get_in_stock_component_ids(session: Session, candidate_ids: List[str]) -> Set[str]:
    """Batch lookup to find which candidate component IDs have available stock."""
    if not candidate_ids:
        return set()

    results = (
        session.query(SupplierStock.component_id)
        .filter(
            SupplierStock.component_id.in_(candidate_ids),
            SupplierStock.is_in_stock == True,  # noqa: E712
            SupplierStock.quantity_available > 0,
        )
        .distinct()
        .all()
    )
    return {str(r[0]) for r in results}


def _passes_constraints(match: Any, resolved_constraints: Dict[str, Any]) -> bool:
    """True if a candidate satisfies every resolved hard constraint.

    Operates on the fields already present on an ``AlternateMatch`` (package,
    pin_count, manufacturer, voltage_min/max), so no extra query is needed.
    Semantics mirror ``COLUMN_MAPPING``:
      • package / pin_count / manufacturer : exact match
      • voltage_min : candidate.voltage_min <= required (window lower bound)
      • voltage_max : candidate.voltage_max >= required (window upper bound)
    A candidate with a missing (None) value fails a constraint on that field.
    """
    for key, value in resolved_constraints.items():
        if value is None or key not in COLUMN_MAPPING:
            continue
        op = COLUMN_MAPPING[key]["op"]
        cand = getattr(match, key, None)
        if cand is None:
            return False
        if op == "eq" and cand != value:
            return False
        if op == "lte" and not (cand <= value):
            return False
        if op == "gte" and not (cand >= value):
            return False
    return True


def alternate_match_node(state: WorkflowState) -> dict:
    """LangGraph node: Dynamic RAG alternate search with batch stock verification."""
    job_id = state["job_id"]
    line_items: list[dict] = [dict(item) for item in state.get("line_items", [])]
    events = list(state.get("events", []))
    
    # User-selected non-negotiable constraints. Two supported shapes:
    #   • value-based: {"voltage_max": 3.3, "package": "LQFP-48"} → enforce the
    #     concrete typed thresholds against each candidate (VALUE mode).
    #   • name-based:  ["package","voltage"] or {"package": true} → "must match
    #     original" semantics resolved per line item (legacy mode).
    raw_constraints = state.get("critical_constraints", {})
    value_constraints = normalize_value_constraints(raw_constraints)

    if value_constraints:
        requested_names = []  # value mode takes precedence
    elif isinstance(raw_constraints, dict):
        requested_names = sorted(k for k, v in raw_constraints.items() if v)
    else:
        requested_names = sorted(raw_constraints or [])
    # Backend-aware compatibility floor: PRD 0.95 with the trained model,
    # a calibrated lower floor with the offline hash fallback.
    threshold = effective_min_similarity()
    out_of_stock = [i for i in line_items if not i.get("is_in_stock")]

    events.append(emit(job_id, "Alternate Match", "start", {
        "out_of_stock_items": len(out_of_stock),
        "threshold": threshold,
        "active_constraints": requested_names,
        "value_constraints": value_constraints,
    }))

    items_needing_approval: list[dict] = []
    session: Session = SessionLocal()

    try:
        for item in out_of_stock:
            original = session.get(Component, item["component_id"]) if item.get("component_id") else None

            events.append(emit(job_id, "Alternate Match", "searching", {"mpn": item["mpn"]}))

            # Build query description from the richest available spec text: the
            # resolved catalog description is authoritative; the BOM line adds
            # signal when it differs.
            bom_desc = (item.get("description") or "").strip()
            catalog_desc = (original.description if original else "").strip()
            if catalog_desc and bom_desc and bom_desc.lower() not in catalog_desc.lower():
                query_description = f"{catalog_desc} {bom_desc}"
            else:
                query_description = catalog_desc or bom_desc

            # Resolve the requested non-negotiable dimensions into concrete
            # {column_key: value} filters using THIS item's original component
            # ("must match original" semantics).
            resolved_constraints = resolve_constraints_for_original(
                requested_names, original
            )

            # Single, calibrated retrieval path (consistent query-vector build
            # and blended scoring). The component-class identity rule is applied
            # as a HARD DB filter here (category_filter) so cross-class parts
            # never enter the candidate pool. Hard user constraints are enforced
            # as a post-filter below so we don't maintain a divergent query.
            original_category = (original.category if original else None) or None
            raw_matches = find_alternates_for_component(
                session,
                mpn=item["mpn"],
                description=query_description,
                category=original_category,
                package=(original.package if original else None),
                pin_count=(original.pin_count if original else None),
                voltage_min=(original.voltage_min if original else None),
                voltage_max=(original.voltage_max if original else None),
                top_k=10,
            )

            # Deterministic cross-parameter sanity guard (belt-and-suspenders):
            # even though the DB query filtered on category, re-verify class
            # identity on every candidate and drop + audit any mismatch. This
            # protects against future query changes and makes the rejection
            # explicit and auditable. Skipped only when the original's class is
            # unknown (nothing to compare against).
            if original_category:
                before = len(raw_matches)
                kept = [m for m in raw_matches if (m.category or "") == original_category]
                rejected = before - len(kept)
                if rejected:
                    events.append(emit(job_id, "Alternate Match", "class_mismatch_rejected", {
                        "mpn": item["mpn"],
                        "original_category": original_category,
                        "rejected": rejected,
                    }))
                raw_matches = kept

            # Enforce the engineer's non-negotiables: drop any candidate that
            # violates a resolved hard constraint before scoring/selection.
            if value_constraints:
                # Keep the class-filtered pool so a fallback pass can re-filter
                # it without re-querying.
                candidate_pool = list(raw_matches)

                # ── Pass 1: enforce ALL user value constraints strictly ──
                strict = [
                    m for m in candidate_pool
                    if _passes_value_constraints(m, value_constraints)
                ]

                if strict:
                    raw_matches = strict
                else:
                    # ── Multi-tier elastic tolerance fallback ──
                    # Progressively widen numeric range bounds (±10% → ±25% →
                    # ±50%) while keeping footprint/identity (eq) strict; then,
                    # if still empty, drop range constraints entirely. Stop at
                    # the first tier that yields candidates. Each tier is
                    # reported via a ``constraints_relaxed`` event.
                    raw_matches = strict  # empty unless a tier succeeds
                    for tier_idx, fraction in enumerate(RELAX_TIERS, start=1):
                        relaxed_constraints, changes = relax_value_constraints(
                            value_constraints, fraction
                        )
                        if not changes:
                            # No relaxable range constraints — tiers can't help;
                            # jump straight to the drop tier below.
                            break
                        tier_matches = [
                            m for m in candidate_pool
                            if _passes_value_constraints(m, relaxed_constraints)
                        ]
                        events.append(emit(job_id, "Alternate Match", "constraints_relaxed", {
                            "mpn": item["mpn"],
                            "reason": "no_candidates_under_strict_constraints",
                            "tier": tier_idx,
                            "widened_by_pct": round(fraction * 100),
                            "relaxed": changes,
                            "candidates_after_relax": len(tier_matches),
                        }))
                        if tier_matches:
                            raw_matches = tier_matches
                            break
                    else:
                        # Widest widening tier still returned nothing — final
                        # tier: drop range constraints, keep exact ones strict.
                        dropped_constraints, dropped = drop_range_constraints(
                            value_constraints
                        )
                        if dropped:
                            drop_matches = [
                                m for m in candidate_pool
                                if _passes_value_constraints(m, dropped_constraints)
                            ]
                            events.append(emit(job_id, "Alternate Match", "constraints_relaxed", {
                                "mpn": item["mpn"],
                                "reason": "range_constraints_dropped",
                                "tier": "final",
                                "dropped": dropped,
                                "candidates_after_relax": len(drop_matches),
                            }))
                            raw_matches = drop_matches
            elif resolved_constraints:
                raw_matches = [
                    m for m in raw_matches
                    if _passes_constraints(m, resolved_constraints)
                ]

            # 1. Blended, spec-aware compatibility (per PRD: voltage, pinout,
            #    package footprint) rather than raw embedding cosine. Score each
            #    candidate against the original component's specs, keep those at
            #    or above the backend-aware floor, and rank by the blended score.
            scored_candidates = []
            for m in raw_matches:
                compat = compatibility_score(
                    semantic=float(m.similarity),
                    target_package=(original.package if original else None),
                    cand_package=m.package,
                    target_pins=(original.pin_count if original else None),
                    cand_pins=m.pin_count,
                    target_vmin=(original.voltage_min if original else None),
                    target_vmax=(original.voltage_max if original else None),
                    cand_vmin=m.voltage_min,
                    cand_vmax=m.voltage_max,
                )
                scored_candidates.append((compat, m))

            scored_candidates.sort(key=lambda t: t[0], reverse=True)
            valid_candidates = [(c, m) for c, m in scored_candidates if c >= threshold]

            if not valid_candidates:
                events.append(emit(job_id, "Alternate Match", "no_alternate", {
                    "mpn": item["mpn"],
                    "reason": "failed_constraints_or_threshold",
                    "candidates_evaluated": len(raw_matches),
                }))
                continue

            # 2. Batched stock check
            candidate_ids = [str(m.component_id) for _, m in valid_candidates]
            in_stock_ids = _get_in_stock_component_ids(session, candidate_ids)

            # 3. Select top-scoring candidate that is actually in stock
            chosen = next(
                ((c, m) for c, m in valid_candidates if str(m.component_id) in in_stock_ids),
                None,
            )

            if chosen is None:
                events.append(emit(job_id, "Alternate Match", "no_alternate", {
                    "mpn": item["mpn"],
                    "reason": "out_of_stock",
                    "candidates_evaluated": len(valid_candidates),
                }))
                continue

            # Populate match payload (chosen is a (blended_compatibility, row) tuple)
            chosen_score, chosen_row = chosen
            item["alternate_component_id"] = str(chosen_row.component_id)
            item["alternate_mpn"] = chosen_row.mpn
            item["alternate_manufacturer"] = chosen_row.manufacturer
            item["alternate_description"] = chosen_row.description
            item["alternate_score"] = float(chosen_score)
            item["needs_approval"] = True
            items_needing_approval.append(item)

            events.append(emit(job_id, "Alternate Match", "alternate_found", {
                "original_mpn": item["mpn"],
                "alternate_mpn": chosen_row.mpn,
                "compatibility_score": float(chosen_score),
            }))

    finally:
        session.close()

    needs_human = len(items_needing_approval) > 0
    events.append(emit(job_id, "Alternate Match", "complete", {
        "alternates_found": len(items_needing_approval),
        "needs_human_approval": needs_human,
    }))

    return {
        "line_items": line_items,
        "items_needing_approval": items_needing_approval,
        "needs_human_approval": needs_human,
        "events": events,
    }