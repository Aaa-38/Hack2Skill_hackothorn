"""Hashing, fingerprinting and HMAC signing helpers.

These functions provide the provenance backbone of the pipeline:

* :func:`candidate_fingerprint` — per-record SHA-256 over the record's canonical
  JSON (excluding the fingerprint field itself), letting downstream pipelines
  detect any mid-flight mutation of a candidate.
* :func:`sha256_file` / :func:`write_sidecar` — per-file integrity hashes.
* :func:`hmac_sign` / :func:`verify_signature` — manifest authentication.

Nothing here introduces non-determinism: hashes depend only on content.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import Any

from src.utils.canonical import canonical_bytes

_FINGERPRINT_FIELD = "candidate_fingerprint"
_CHUNK = 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    """Return the hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Return the hex SHA-256 digest of a file, streamed in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def candidate_fingerprint(record: dict[str, Any]) -> str:
    """Compute the SHA-256 fingerprint of a candidate record.

    The fingerprint field itself is excluded so that storing the result back on
    the record does not change the value, keeping it stable and verifiable.

    Args:
        record: The candidate record (may or may not already carry a
            fingerprint field).

    Returns:
        Hex SHA-256 digest of the record's canonical JSON.
    """
    payload = {k: v for k, v in record.items() if k != _FINGERPRINT_FIELD}
    return sha256_bytes(canonical_bytes(payload))


def write_sidecar(path: str | Path) -> str:
    """Write ``<path>.sha256`` containing the file's digest; return the digest."""
    path = Path(path)
    digest = sha256_file(path)
    sidecar = path.with_name(path.name + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def hmac_sign(payload: bytes, key: str) -> str:
    """Return the hex HMAC-SHA256 signature of ``payload`` under ``key``."""
    return hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, key: str, signature: str) -> bool:
    """Constant-time check that ``signature`` matches ``payload`` under ``key``."""
    expected = hmac_sign(payload, key)
    return hmac.compare_digest(expected, signature)
