"""Transformation step.

Turns a cleaned, nested record into the flat-ish transformed record that forms
the immutable contract for Pipeline 2:

* **Flatten** scalar leaves of configured objects to prefixed top-level keys
  (``profile.years_of_experience`` → ``profile_years_of_experience``). Objects
  that still hold non-scalar data (``redrob_signals`` with its nested dicts) are
  *also* kept intact and untouched; fully-scalar objects (``profile``) are not
  duplicated.
* **Preserve** complex lists (``skills``, ``career_history`` …) verbatim for P2.
* **Build** ``candidate_document`` by ordered concatenation of existing text
  only — no generated, summarized or hallucinated content.
* **Pass through** unknown top-level fields untouched.
* **Stamp lineage** in ``_pipeline_metadata``.

The ``features`` namespace is reserved here and filled by the feature step, so
generated features never mix with ``redrob_signals``.
"""

from __future__ import annotations

from typing import Any

from src.pipeline1.config import Settings
from src.pipeline1.ports import RawCandidate, Step


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


class TransformationStep(Step):
    """Flatten scalars, preserve lists, and build the candidate document."""

    name = "transformation"

    def __init__(self, settings: Settings) -> None:
        self._flatten = settings.transformation.flatten
        self._preserve_lists = settings.transformation.preserve_lists
        self._separator = settings.transformation.document_separator
        self._fields_transformed = 0
        self._documents_built = 0
        # Top-level keys we consume explicitly; everything else is pass-through.
        self._handled = (
            {"candidate_id"}
            | set(self._flatten)
            | set(self._preserve_lists)
        )

    def process(self, record: RawCandidate) -> dict[str, Any]:
        """Build and return the transformed record for ``record``."""
        out: dict[str, Any] = {"candidate_id": record.get("candidate_id")}

        # 1. Flatten configured objects' scalar leaves.
        for obj_key, prefix in self._flatten.items():
            obj = record.get(obj_key)
            if not isinstance(obj, dict):
                continue
            has_non_scalar = False
            for leaf_key, leaf_val in obj.items():
                if _is_scalar(leaf_val):
                    out[f"{prefix}_{leaf_key}"] = leaf_val
                    self._fields_transformed += 1
                else:
                    has_non_scalar = True
            # Keep the original object only if it still carries non-scalar data
            # (this is what "leave redrob_signals untouched" requires).
            if has_non_scalar:
                out[obj_key] = obj

        # 2. Preserve complex lists intact for Pipeline 2.
        for list_key in self._preserve_lists:
            out[list_key] = record.get(list_key, [])

        # 3. Pass through any unknown extra top-level fields.
        for key, value in record.items():
            if key not in self._handled and key not in out:
                out[key] = value

        # 4. Deterministic candidate_document (existing text only).
        out["candidate_document"] = self._build_document(record)
        self._documents_built += 1

        # 5. Reserved namespace + lineage.
        out.setdefault("features", {})
        out["_pipeline_metadata"] = {
            "validated": True,
            "cleaned": True,
            "quality_checked": True,
            "transformed": True,
            "feature_generated": False,
        }
        return out

    def _build_document(self, record: RawCandidate) -> str:
        """Concatenate headline, summary, current role and career text."""
        profile = record.get("profile", {}) if isinstance(record.get("profile"), dict) else {}
        parts: list[str] = [
            profile.get("headline", ""),
            profile.get("summary", ""),
            profile.get("current_title", ""),
            profile.get("current_company", ""),
        ]
        career = record.get("career_history", [])
        if isinstance(career, list):
            for entry in career:
                if isinstance(entry, dict):
                    parts.append(entry.get("title", ""))
                    parts.append(entry.get("description", ""))
        return self._separator.join(p for p in parts if isinstance(p, str) and p)

    def report(self) -> dict[str, Any]:
        return {
            "fields_transformed": self._fields_transformed,
            "documents_built": self._documents_built,
        }
