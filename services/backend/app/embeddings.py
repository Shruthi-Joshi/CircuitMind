"""Embedding generation with a graceful offline fallback.

Primary path uses `sentence-transformers/all-MiniLM-L6-v2` (384-dim). When the model
cannot be loaded (no network, missing weights), we fall back to a deterministic
hash-based embedding of the same dimension so the whole pipeline stays runnable.
"""
from __future__ import annotations

import hashlib
import math
import threading
from typing import Iterable

from .config import settings

_model = None
_model_lock = threading.Lock()
_load_failed = False


def _try_load_model():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    with _model_lock:
        if _model is not None or _load_failed:
            return _model
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            _model = SentenceTransformer(settings.embedding_model)
        except Exception as exc:  # pragma: no cover - environment dependent
            print(f"[embeddings] falling back to hash embeddings: {exc}")
            _load_failed = True
            _model = None
    return _model


def _hash_embed(text: str, dim: int) -> list[float]:
    """Deterministic bag-of-tokens hash embedding, L2-normalized."""
    vec = [0.0] * dim
    tokens = [t for t in _tokenize(text)] or [text.strip().lower()]
    for tok in tokens:
        h = hashlib.sha256(tok.encode("utf-8")).digest()
        # Spread each token across a few buckets for a denser signal.
        for i in range(8):
            idx = int.from_bytes(h[i * 2 : i * 2 + 2], "little") % dim
            sign = 1.0 if h[i] % 2 == 0 else -1.0
            vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _tokenize(text: str) -> list[str]:
    out, cur = [], []
    for ch in text.lower():
        if ch.isalnum():
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def embed(text: str) -> list[float]:
    """Return a single 384-dim embedding for `text`."""
    return embed_batch([text])[0]


# Backend identifiers for the active embedding strategy.
BACKEND_MODEL = "model"  # real sentence-transformers model (e.g. all-MiniLM-L6-v2)
BACKEND_HASH = "hash"    # deterministic offline hash fallback


def active_backend() -> str:
    """Return which embedding backend is currently in effect.

    Attempts to load the real model (once, cached); returns ``BACKEND_MODEL``
    when available and ``BACKEND_HASH`` when the offline hash fallback is in
    use. Callers can use this to calibrate similarity thresholds, since hash
    embeddings produce lower cosine similarities than a trained model for the
    same semantic distance.
    """
    return BACKEND_MODEL if _try_load_model() is not None else BACKEND_HASH


def is_real_model_active() -> bool:
    """Convenience predicate: True when the trained model is in use."""
    return active_backend() == BACKEND_MODEL


def embed_batch(texts: Iterable[str]) -> list[list[float]]:
    texts = [t if t and t.strip() else " " for t in texts]
    model = _try_load_model()
    if model is not None:
        vectors = model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]
    return [_hash_embed(t, settings.embedding_dim) for t in texts]
