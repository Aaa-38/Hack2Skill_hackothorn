"""Output adapters: streaming JSONL writer and report writer.

The :class:`JsonlWriter` writes one canonical JSON record per line so that the
resulting file is deterministic and hashable. Reports are written as readable
(but still canonical-key-sorted) JSON; reports are not hashed, so their embedded
timings do not affect data reproducibility.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.utils.canonical import canonical_bytes


class JsonlWriter:
    """Append-only writer emitting one canonical JSON object per line."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "wb")
        self.rows = 0

    def write(self, record: dict[str, Any]) -> None:
        """Append ``record`` as a canonical JSON line."""
        self._fh.write(canonical_bytes(record))
        self._fh.write(b"\n")
        self.rows += 1

    def close(self) -> None:
        """Flush and close the file handle (idempotent)."""
        if not self._fh.closed:
            self._fh.flush()
            self._fh.close()

    def __enter__(self) -> "JsonlWriter":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def write_report(path: str | Path, payload: dict[str, Any]) -> None:
    """Write a transparency report as human-readable, key-sorted JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
