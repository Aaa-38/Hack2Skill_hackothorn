"""Manifest construction, signing and verification.

The manifest chains provenance from Pipeline 0 (the input artifact's SHA-256)
through every Pipeline 1 output (filename, sha256, row_count, stage). It records
run metadata (timestamp, git commit, config hash) and is signed with HMAC-SHA256
so tampering with either the outputs or the manifest itself is detectable.

Run metadata (timestamps, git commit) lives only here — never in data records.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.utils.canonical import canonical_bytes
from src.utils.integrity import (
    hmac_sign,
    sha256_file,
    verify_signature,
    write_sidecar,
)

_SIGNATURE_KEY = "signature"


def _git_commit() -> str | None:
    """Return the current git commit hash, or ``None`` when not a repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def build_manifest(
    outputs: list[dict[str, Any]],
    input_path: str | Path,
    input_sha256: str,
    config_hash: str,
    hmac_key: str,
) -> dict[str, Any]:
    """Build and sign the manifest for a run.

    Args:
        outputs: One dict per output file with at least ``filename``, ``sha256``,
            ``row_count`` and ``stage``.
        input_path: The ingestion input file.
        input_sha256: SHA-256 of the input artifact (P0→P1 lineage anchor).
        config_hash: Hash of the run configuration.
        hmac_key: Key used to sign the manifest.

    Returns:
        The signed manifest dict (the ``signature`` field is the HMAC over the
        canonical manifest body sans signature).
    """
    body = {
        "pipeline": "redrob-pipeline1",
        "pass": 1,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "config_hash": config_hash,
        "input": {
            "filename": str(Path(input_path).name),
            "path": str(input_path),
            "sha256": input_sha256,
        },
        "outputs": sorted(outputs, key=lambda o: o["filename"]),
    }
    signature = hmac_sign(canonical_bytes(body), hmac_key)
    manifest = dict(body)
    manifest[_SIGNATURE_KEY] = signature
    return manifest


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> str:
    """Write the manifest as canonical JSON and its ``.sha256`` sidecar.

    Returns:
        The SHA-256 digest of the written manifest file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(manifest))
    return write_sidecar(path)


def verify_manifest(
    manifest_path: str | Path, hmac_key: str
) -> tuple[bool, list[dict[str, Any]]]:
    """Verify signature and every output hash recorded in a manifest.

    Args:
        manifest_path: Path to ``manifest.json``.
        hmac_key: Key the manifest was signed with.

    Returns:
        ``(all_passed, results)`` where ``results`` has one entry per check
        (signature + each output file) with a ``status`` of ``PASS``/``FAIL``.
    """
    import json

    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text("utf-8"))
    results: list[dict[str, Any]] = []
    all_passed = True

    signature = manifest.get(_SIGNATURE_KEY, "")
    body = {k: v for k, v in manifest.items() if k != _SIGNATURE_KEY}
    sig_ok = verify_signature(canonical_bytes(body), hmac_key, signature)
    all_passed &= sig_ok
    results.append(
        {"check": "signature", "status": "PASS" if sig_ok else "FAIL"}
    )

    base = manifest_path.parent
    for out in manifest.get("outputs", []):
        fname = out["filename"]
        expected = out["sha256"]
        fpath = base / fname
        if not fpath.exists():
            ok = False
            actual = None
        else:
            actual = sha256_file(fpath)
            ok = actual == expected
        all_passed &= ok
        results.append(
            {
                "check": fname,
                "status": "PASS" if ok else "FAIL",
                "expected": expected,
                "actual": actual,
            }
        )

    return all_passed, results
