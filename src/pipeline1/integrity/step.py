"""Integrity step — per-record fingerprinting.

Stamps each record with ``candidate_fingerprint`` = SHA-256 of the record's
canonical JSON (excluding the fingerprint field). Downstream pipelines can
recompute it to detect any mid-flight mutation of a candidate.
"""

from __future__ import annotations

from typing import Any

from src.pipeline1.ports import Step
from src.utils.integrity import candidate_fingerprint


class IntegrityStep(Step):
    """Add a stable per-record fingerprint."""

    name = "integrity"

    def __init__(self) -> None:
        self._records = 0

    def process(self, record: dict[str, Any]) -> dict[str, Any]:
        """Add ``candidate_fingerprint`` to ``record`` in place and return it."""
        record["candidate_fingerprint"] = candidate_fingerprint(record)
        self._records += 1
        return record

    def report(self) -> dict[str, Any]:
        return {"records_fingerprinted": self._records}
