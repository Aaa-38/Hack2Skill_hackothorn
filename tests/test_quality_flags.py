"""Pass 2: quality flags — each rule triggers; records are kept, never dropped."""

from __future__ import annotations

from src.pipeline1.config import QualityThresholds
from src.pipeline1.validation.quality_flags import QualityFlagStep


def _flags(record: dict) -> list[str]:
    return QualityFlagStep(QualityThresholds()).process(record)["quality_flags"]


def test_clean_record_has_no_flags():
    rec = {
        "profile": {"years_of_experience": 5.0},
        "career_history": [
            {"start_date": "2020-01-01", "end_date": "2024-01-01", "duration_months": 48}
        ],
        "skills": [{"normalized_name": "python", "proficiency": "expert", "duration_months": 60}],
        "redrob_signals": {"last_active_date": "2026-06-01"},
    }
    assert _flags(rec) == []


def test_impossible_tenure():
    # yoe=2 → limit = 2*12*1.5 + 24 = 60; 120 > 60 → flagged.
    rec = {
        "profile": {"years_of_experience": 2.0},
        "career_history": [{"duration_months": 120, "start_date": "2015-01-01"}],
    }
    assert "impossible_tenure" in _flags(rec)


def test_expert_zero_experience():
    rec = {
        "skills": [
            {"normalized_name": f"s{i}", "proficiency": "expert", "duration_months": 0}
            for i in range(5)
        ]
    }
    assert "expert_zero_experience" in _flags(rec)


def test_overlapping_roles():
    rec = {
        "career_history": [
            {"start_date": "2020-01-01", "end_date": "2022-01-01"},
            {"start_date": "2021-01-01", "end_date": "2023-01-01"},
        ]
    }
    assert "overlapping_roles" in _flags(rec)


def test_future_dates():
    rec = {"career_history": [{"start_date": "2030-01-01", "end_date": None}]}
    assert "future_dates" in _flags(rec)


def test_negative_or_invalid_values():
    rec = {"skills": [{"normalized_name": "x", "endorsements": -1}]}
    assert "negative_or_invalid_values" in _flags(rec)


def test_duplicate_skills():
    rec = {
        "skills": [
            {"normalized_name": "python"},
            {"normalized_name": "python"},
        ]
    }
    assert "duplicate_skills" in _flags(rec)


def test_report_counts_flags():
    step = QualityFlagStep(QualityThresholds())
    step.process({"skills": [{"normalized_name": "a"}, {"normalized_name": "a"}]})
    step.process({"profile": {"years_of_experience": 5.0}})  # no flags
    rep = step.report()
    assert rep["total_candidates_processed"] == 2
    assert rep["candidates_with_flags"] == 1
    assert rep["flag_counts"]["duplicate_skills"] == 1
    assert set(rep["flag_counts"]) == {
        "impossible_tenure",
        "expert_zero_experience",
        "overlapping_roles",
        "future_dates",
        "negative_or_invalid_values",
        "duplicate_skills",
    }
