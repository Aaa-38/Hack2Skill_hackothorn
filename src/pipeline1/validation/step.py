"""Schema validation step.

Hard structural failures (missing required field, uncoercible type, bad
``candidate_id`` pattern, wrong cardinality) make a record ``error`` → it is
quarantined with the precise pydantic issues. Soft issues (unknown extra fields)
make a record ``warning`` → it is kept with a ``schema_warning`` flag. Truly
clean records are ``valid``. Nothing is ever silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from src.pipeline1.ports import RawCandidate, Step
from src.pipeline1.validation.models import Candidate

Severity = Literal["valid", "warning", "error"]

# Known top-level keys; anything else is a pass-through extra → schema_warning.
_KNOWN_TOP_LEVEL = {
    "candidate_id",
    "profile",
    "career_history",
    "education",
    "skills",
    "certifications",
    "languages",
    "redrob_signals",
}


@dataclass
class ValidationResult:
    """Outcome of validating one raw record."""

    status: Severity
    record: RawCandidate
    issues: list[dict[str, Any]] = field(default_factory=list)
    candidate_id: str | None = None


class ValidationStep(Step):
    """Validate raw records against :class:`Candidate`."""

    name = "validation"

    def __init__(self) -> None:
        self._valid = 0
        self._warning = 0
        self._error = 0
        self._total_issues = 0

    def process(self, record: RawCandidate, line_no: int) -> ValidationResult:
        """Validate a single raw record.

        Args:
            record: Parsed candidate dict from ingestion.
            line_no: Source line number, attached to error issues for tracing.

        Returns:
            A :class:`ValidationResult`. On ``error`` the original record is kept
            so it can be quarantined verbatim with its reasons.
        """
        cid = record.get("candidate_id")
        try:
            Candidate.model_validate(record)
        except ValidationError as exc:
            issues = [
                {
                    "line": line_no,
                    "location": ".".join(str(p) for p in err["loc"]),
                    "type": err["type"],
                    "message": err["msg"],
                }
                for err in exc.errors()
            ]
            self._error += 1
            self._total_issues += len(issues)
            return ValidationResult(
                status="error",
                record=record,
                issues=issues,
                candidate_id=cid if isinstance(cid, str) else None,
            )

        extras = sorted(k for k in record if k not in _KNOWN_TOP_LEVEL)
        if extras:
            self._warning += 1
            issue = {
                "line": line_no,
                "location": "<root>",
                "type": "schema_warning",
                "message": f"unknown pass-through fields: {extras}",
            }
            self._total_issues += 1
            return ValidationResult(
                status="warning",
                record=record,
                issues=[issue],
                candidate_id=str(cid),
            )

        self._valid += 1
        return ValidationResult(status="valid", record=record, candidate_id=str(cid))

    def report(self) -> dict[str, Any]:
        return {
            "records_valid": self._valid,
            "records_warning": self._warning,
            "records_error": self._error,
            "total_issues": self._total_issues,
        }
