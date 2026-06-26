"""Canonical JSON serialization.

Determinism is the contract of this pipeline: the same logical object MUST
serialize to byte-identical output on every run, machine, and Python build so
that SHA-256 hashes are reproducible. We therefore fix every degree of freedom:

* keys sorted lexicographically at every nesting level,
* compact separators (no insignificant whitespace),
* UTF-8 output without ASCII escaping (``ensure_ascii=False`` semantics),
* stable float formatting.

``orjson`` (Rust core) is used when available for speed and a stable shortest
float repr; the stdlib ``json`` fallback is configured to match byte-for-byte
for the data shapes this pipeline produces.
"""

from __future__ import annotations

import json
from typing import Any

try:  # optional, but strongly preferred for speed + stable float repr
    import orjson

    _HAVE_ORJSON = True
except ImportError:  # pragma: no cover - exercised only when orjson absent
    orjson = None  # type: ignore[assignment]
    _HAVE_ORJSON = False


def canonical_bytes(obj: Any) -> bytes:
    """Serialize ``obj`` to canonical, deterministic JSON bytes (UTF-8).

    Args:
        obj: Any JSON-serializable object (dict, list, scalars).

    Returns:
        UTF-8 encoded canonical JSON with sorted keys and compact separators.
    """
    if _HAVE_ORJSON:
        # OPT_SORT_KEYS sorts keys at all levels; orjson emits compact UTF-8.
        return orjson.dumps(obj, option=orjson.OPT_SORT_KEYS)
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_str(obj: Any) -> str:
    """Return :func:`canonical_bytes` decoded as a UTF-8 string."""
    return canonical_bytes(obj).decode("utf-8")


def loads(data: bytes | str) -> Any:
    """Parse JSON from ``bytes`` or ``str`` using the fastest available codec."""
    if _HAVE_ORJSON:
        return orjson.loads(data)
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return json.loads(data)
