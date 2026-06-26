"""Skill normalization.

Maps each skill name through ``config/skill_mappings.yaml`` and stores the
canonical form as ``normalized_name`` alongside the original ``name`` (which is
preserved verbatim). Unknown skills fall back to their casefolded cleaned name,
so a skill is never dropped — only canonicalized.
"""

from __future__ import annotations

from typing import Any

from src.pipeline1.cleaning.text import normalize_key


class SkillNormalizer:
    """Add ``normalized_name`` to skill dicts using a configured alias map."""

    def __init__(self, mappings: dict[str, str]) -> None:
        # Keys are already casefolded by the config loader.
        self._mappings = mappings
        self.normalized_count = 0

    def normalize(self, skill: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of ``skill`` with a ``normalized_name`` added.

        Args:
            skill: A skill dict with at least a ``name`` key.

        Returns:
            A new dict; ``name`` is untouched, ``normalized_name`` is the mapped
            or fallback canonical form.
        """
        name = skill.get("name", "")
        key = normalize_key(name) if isinstance(name, str) else ""
        canonical = self._mappings.get(key, key)
        if canonical != key or key in self._mappings:
            self.normalized_count += 1
        out = dict(skill)
        out["normalized_name"] = canonical
        return out
