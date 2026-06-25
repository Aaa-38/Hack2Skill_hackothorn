"""Cleaning step.

Responsibilities (all non-destructive — nothing is dropped silently):

* **Deduplication** by ``candidate_id`` (keep first; later copies are reported
  with ``duplicate_of``). The seen-id set is the only unbounded in-memory state.
* **Null handling** — configured fields backfilled with configured defaults.
* **String / text normalization** — NFKC + control-strip + whitespace collapse
  on every string. Free text (``summary``, ``career_history[].description``) is
  touched only by this whitespace/Unicode normalization, never lowercased.
* **Date normalization** — configured date fields parsed via ``dateutil`` to ISO
  ``YYYY-MM-DD``; unparseable values become ``null`` plus a warning.
* **Skill normalization** — delegated to :class:`SkillNormalizer`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dateutil import parser as date_parser

from src.pipeline1.cleaning.skill_normalizer import SkillNormalizer
from src.pipeline1.cleaning.text import normalize_text
from src.pipeline1.config import Settings
from src.pipeline1.ports import RawCandidate, Step


@dataclass
class CleaningResult:
    """Outcome of cleaning one record."""

    record: RawCandidate
    is_duplicate: bool = False
    duplicate_of: str | None = None
    nulls_fixed: int = 0
    dates_invalid: int = 0
    issues: list[dict[str, Any]] = field(default_factory=list)


class CleaningStep(Step):
    """Normalize, de-duplicate and date-fix validated records."""

    name = "cleaning"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._defaults = settings.cleaning.defaults
        self._date_fields = settings.cleaning.date_fields
        self._normalizer = SkillNormalizer(settings.skill_mappings)
        self._seen: set[str] = set()
        self._duplicates = 0
        self._nulls_fixed = 0
        self._dates_invalid = 0

    # -- public API -------------------------------------------------------

    def process(self, record: RawCandidate) -> CleaningResult:
        """Clean a single (already validated) record.

        Returns a :class:`CleaningResult`; duplicates are flagged rather than
        cleaned so they can be routed to the error sink with ``duplicate_of``.
        """
        cid = record.get("candidate_id")
        if isinstance(cid, str):
            if cid in self._seen:
                self._duplicates += 1
                return CleaningResult(
                    record=record, is_duplicate=True, duplicate_of=cid
                )
            self._seen.add(cid)

        result = CleaningResult(record=record)
        self._apply_defaults(record, result)
        _normalize_strings(record)
        self._normalize_dates(record, result)
        self._normalize_skills(record)
        return result

    @property
    def skills_normalized(self) -> int:
        return self._normalizer.normalized_count

    def report(self) -> dict[str, Any]:
        return {
            "duplicates_removed": self._duplicates,
            "null_values_fixed": self._nulls_fixed,
            "dates_invalidated": self._dates_invalid,
            "skills_normalized": self._normalizer.normalized_count,
        }

    # -- internals --------------------------------------------------------

    def _apply_defaults(self, record: RawCandidate, result: CleaningResult) -> None:
        """Backfill configured ``a.b`` paths that are missing or null."""
        for dotted, default in self._defaults.items():
            parent, leaf = _resolve_parent(record, dotted)
            if parent is None:
                continue
            if parent.get(leaf) is None:
                parent[leaf] = default
                self._nulls_fixed += 1
                result.nulls_fixed += 1

    def _normalize_dates(self, record: RawCandidate, result: CleaningResult) -> None:
        """Coerce configured date fields to ISO ``YYYY-MM-DD`` strings."""
        for pattern in self._date_fields:
            for parent, leaf in _iter_targets(record, pattern):
                value = parent.get(leaf)
                if value is None or value == "":
                    continue
                iso = _to_iso_date(value)
                if iso is None:
                    parent[leaf] = None
                    self._dates_invalid += 1
                    result.dates_invalid += 1
                    result.issues.append(
                        {
                            "type": "date_unparseable",
                            "location": pattern,
                            "message": f"could not parse date {value!r}",
                        }
                    )
                else:
                    parent[leaf] = iso

    def _normalize_skills(self, record: RawCandidate) -> None:
        skills = record.get("skills")
        if isinstance(skills, list):
            record["skills"] = [
                self._normalizer.normalize(s) if isinstance(s, dict) else s
                for s in skills
            ]


# -- module-level helpers (pure, unit-testable) ---------------------------


def _normalize_strings(obj: Any) -> None:
    """Recursively normalize every string leaf in place (values, not keys)."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str):
                obj[key] = normalize_text(value)
            else:
                _normalize_strings(value)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            if isinstance(value, str):
                obj[i] = normalize_text(value)
            else:
                _normalize_strings(value)


def _to_iso_date(value: Any) -> str | None:
    """Parse ``value`` into ISO ``YYYY-MM-DD``; return ``None`` if unparseable."""
    if not isinstance(value, str):
        return None
    try:
        return date_parser.parse(value).date().isoformat()
    except (ValueError, OverflowError, TypeError):
        return None


def _resolve_parent(record: dict[str, Any], dotted: str) -> tuple[dict | None, str]:
    """Resolve a non-list dotted path to ``(parent_dict, leaf_key)``."""
    parts = dotted.split(".")
    cur: Any = record
    for part in parts[:-1]:
        if not isinstance(cur, dict):
            return None, parts[-1]
        cur = cur.get(part)
    if not isinstance(cur, dict):
        return None, parts[-1]
    return cur, parts[-1]


def _iter_targets(record: dict[str, Any], pattern: str):
    """Yield ``(parent_dict, leaf_key)`` for a path that may contain one ``[]``.

    Supports patterns like ``career_history[].start_date`` (iterate the list)
    and plain dotted paths like ``redrob_signals.signup_date``.
    """
    if "[]" in pattern:
        list_path, _, leaf = pattern.partition("[].")
        container = record
        for part in list_path.split("."):
            if not isinstance(container, dict):
                return
            container = container.get(part)
        if isinstance(container, list):
            for item in container:
                if isinstance(item, dict):
                    yield item, leaf
        return
    parent, leaf = _resolve_parent(record, pattern)
    if parent is not None:
        yield parent, leaf
