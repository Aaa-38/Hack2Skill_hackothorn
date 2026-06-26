"""Pipeline 0 — streaming JSONL ingestion.

:class:`JsonlReader` reads ``.jsonl`` or ``.jsonl.gz`` line by line without ever
loading the whole file into memory. Malformed lines are routed to a parse-error
sink (line number + raw snippet) and ingestion continues — nothing is silently
dropped, and one bad line never aborts a 100k-record run.
"""

from __future__ import annotations

import gzip
import io
from pathlib import Path
from typing import Callable, Iterator

from src.pipeline1.ports import RawCandidate
from src.utils.canonical import loads

# Cap stored raw snippets so a pathological line cannot bloat the error file.
_SNIPPET_LIMIT = 500


class JsonlReader:
    """Stream candidate records from a JSONL or gzipped-JSONL file.

    Args:
        path: Path to a ``.jsonl`` or ``.jsonl.gz`` file.
        on_parse_error: Callback invoked as ``(line_number, raw_snippet, error)``
            for each line that fails to parse. Ingestion continues afterwards.
    """

    def __init__(
        self,
        path: str | Path,
        on_parse_error: Callable[[int, str, str], None] | None = None,
    ) -> None:
        self.path = Path(path)
        self._on_parse_error = on_parse_error
        self.lines_read = 0
        self.parse_errors = 0

    def _open(self) -> io.TextIOBase:
        """Open the file transparently handling gzip, UTF-8, line by line."""
        if self.path.suffix == ".gz":
            return io.TextIOWrapper(
                gzip.open(self.path, "rb"), encoding="utf-8", errors="replace"
            )
        return open(self.path, "r", encoding="utf-8", errors="replace")

    def __iter__(self) -> Iterator[tuple[int, RawCandidate]]:
        """Yield ``(line_number, record)`` for every well-formed line.

        Blank lines are skipped. Malformed lines invoke ``on_parse_error`` and
        are not yielded.
        """
        with self._open() as fh:
            for line_no, raw in enumerate(fh, start=1):
                self.lines_read = line_no
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    record = loads(stripped)
                except Exception as exc:  # noqa: BLE001 - any parse failure
                    self.parse_errors += 1
                    if self._on_parse_error is not None:
                        self._on_parse_error(
                            line_no, stripped[:_SNIPPET_LIMIT], str(exc)
                        )
                    continue
                if not isinstance(record, dict):
                    self.parse_errors += 1
                    if self._on_parse_error is not None:
                        self._on_parse_error(
                            line_no,
                            stripped[:_SNIPPET_LIMIT],
                            "line is not a JSON object",
                        )
                    continue
                yield line_no, record
