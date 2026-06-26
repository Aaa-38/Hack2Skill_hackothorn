"""Ports (interfaces) for the pipeline.

Following clean architecture, use-case Steps and the orchestrator depend only on
these abstractions, never on concrete file readers/writers. Adapters in the
``ingestion`` package and the writers in :mod:`src.pipeline1.pipeline` implement
them. Steps are independently unit-testable because they take plain dicts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator, Protocol, runtime_checkable

# A parsed-but-unvalidated candidate record straight from ingestion.
RawCandidate = dict[str, Any]


@runtime_checkable
class RecordReader(Protocol):
    """A streaming source of raw records."""

    def __iter__(self) -> Iterator[tuple[int, RawCandidate]]:
        """Yield ``(line_number, record)`` pairs, one per parsed line."""
        ...


@runtime_checkable
class RecordWriter(Protocol):
    """A sink that appends canonical JSON records line by line."""

    def write(self, record: dict[str, Any]) -> None:
        """Append a single record."""
        ...

    def close(self) -> None:
        """Flush and close the underlying handle."""
        ...


class Step(ABC):
    """A single, independent pipeline stage.

    Each Step owns its own running report counters. Steps are composed by the
    orchestrator but never call each other directly, satisfying the
    single-responsibility and dependency-inversion principles.
    """

    name: str = "step"

    @abstractmethod
    def report(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of this step's counters."""
        raise NotImplementedError
