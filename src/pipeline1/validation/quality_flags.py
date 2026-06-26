"""Quality flag step (Pass 2).

Runs after cleaning, before transformation. Appends a ``quality_flags`` list to
every record — records are **kept, never dropped**; Pipeline 3 consumes the
flags to down-weight or filter. All thresholds are configurable
(``quality_thresholds`` in ``settings.yaml``); the future-date reference is a
fixed config date so the flag stays deterministic and hash-stable.

Flags: ``impossible_tenure``, ``expert_zero_experience``, ``overlapping_roles``,
``future_dates``, ``negative_or_invalid_values``, ``duplicate_skills``.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from src.pipeline1.config import QualityThresholds
from src.pipeline1.ports import RawCandidate, Step

_FLAGS = (
    "impossible_tenure",
    "expert_zero_experience",
    "overlapping_roles",
    "future_dates",
    "negative_or_invalid_values",
    "duplicate_skills",
)


def _parse_iso(value: Any) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` string to a date; ``None`` if not parseable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class QualityFlagStep(Step):
    """Attach deterministic quality flags to a cleaned record."""

    name = "quality_flags"

    def __init__(self, thresholds: QualityThresholds) -> None:
        self._t = thresholds
        self._reference = _parse_iso(thresholds.reference_date) or date.max
        self._total = 0
        self._with_flags = 0
        self._counts: Counter[str] = Counter()

    def process(self, record: RawCandidate) -> RawCandidate:
        """Compute flags and append ``record['quality_flags']`` in place."""
        self._total += 1
        career = record.get("career_history") or []
        skills = record.get("skills") or []
        profile = record.get("profile") or {}
        signals = record.get("redrob_signals") or {}

        # Parse each career entry's dates once and reuse across the date rules.
        parsed: list[tuple[date | None, date | None]] = []
        for c in career:
            if isinstance(c, dict):
                parsed.append((_parse_iso(c.get("start_date")), _parse_iso(c.get("end_date"))))

        flags: list[str] = []
        if self._impossible_tenure(career, profile):
            flags.append("impossible_tenure")
        if self._expert_zero_experience(skills):
            flags.append("expert_zero_experience")
        if self._overlapping_roles(parsed):
            flags.append("overlapping_roles")
        if self._future_dates(parsed, signals):
            flags.append("future_dates")
        if self._negative_or_invalid(career, skills, profile):
            flags.append("negative_or_invalid_values")
        if self._duplicate_skills(skills):
            flags.append("duplicate_skills")

        record["quality_flags"] = flags
        if flags:
            self._with_flags += 1
            self._counts.update(flags)
        return record

    # -- individual flag rules -------------------------------------------

    def _impossible_tenure(self, career: list, profile: dict) -> bool:
        total_months = sum(
            int(c.get("duration_months", 0))
            for c in career
            if isinstance(c, dict) and isinstance(c.get("duration_months"), (int, float))
        )
        yoe = profile.get("years_of_experience")
        if not isinstance(yoe, (int, float)):
            return False
        limit = yoe * 12 * self._t.impossible_tenure_factor + self._t.impossible_tenure_buffer_months
        return total_months > limit

    def _expert_zero_experience(self, skills: list) -> bool:
        count = sum(
            1
            for s in skills
            if isinstance(s, dict)
            and s.get("proficiency") == "expert"
            and s.get("duration_months") == 0
        )
        return count >= self._t.expert_zero_experience_min_skills

    def _overlapping_roles(self, parsed: list[tuple[date | None, date | None]]) -> bool:
        # null/unparseable start → skip; null end → ongoing (date.max).
        ranges = [(s, e or date.max) for s, e in parsed if s is not None]
        for i in range(len(ranges)):
            s_a, e_a = ranges[i]
            for j in range(i + 1, len(ranges)):
                s_b, e_b = ranges[j]
                if s_a < e_b and e_a > s_b:
                    return True
        return False

    def _future_dates(
        self, parsed: list[tuple[date | None, date | None]], signals: dict
    ) -> bool:
        last_active = _parse_iso(signals.get("last_active_date"))
        if last_active is not None and last_active > self._reference:
            return True
        for start, end in parsed:
            if (start is not None and start > self._reference) or (
                end is not None and end > self._reference
            ):
                return True
        return False

    def _negative_or_invalid(self, career: list, skills: list, profile: dict) -> bool:
        yoe = profile.get("years_of_experience")
        if isinstance(yoe, (int, float)) and yoe < 0:
            return True
        for s in skills:
            if isinstance(s, dict):
                end = s.get("endorsements")
                dur = s.get("duration_months")
                if isinstance(end, (int, float)) and end < 0:
                    return True
                if isinstance(dur, (int, float)) and dur < 0:
                    return True
        for c in career:
            if isinstance(c, dict):
                dur = c.get("duration_months")
                if isinstance(dur, (int, float)) and dur < 0:
                    return True
        return False

    def _duplicate_skills(self, skills: list) -> bool:
        seen: set[str] = set()
        for s in skills:
            if not isinstance(s, dict):
                continue
            name = s.get("normalized_name")
            if isinstance(name, str):
                if name in seen:
                    return True
                seen.add(name)
        return False

    # -- report -----------------------------------------------------------

    def report(self) -> dict[str, Any]:
        return {
            "total_candidates_processed": self._total,
            "candidates_with_flags": self._with_flags,
            "flag_counts": {flag: self._counts.get(flag, 0) for flag in _FLAGS},
        }
