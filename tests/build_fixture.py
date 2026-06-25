"""Generate the deterministic test fixture ``tests/fixtures/sample.jsonl``.

The fixture deliberately exercises every routing path: valid records, a
duplicate, a schema-invalid (missing-field) record, messy casing/whitespace,
unparseable and messy dates, an unknown pass-through field, and a record with a
rich verbatim ``career_history[].description``. One line is intentionally
malformed JSON. Run with ``python -m tests.build_fixture``.
"""

from __future__ import annotations

import json
from pathlib import Path

_FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


def _career(company: str, title: str, start: str, end: str | None, desc: str) -> dict:
    return {
        "company": company,
        "title": title,
        "start_date": start,
        "end_date": end,
        "duration_months": 24,
        "is_current": end is None,
        "industry": "Software",
        "company_size": "201-500",
        "description": desc,
    }


def _signals(**over) -> dict:
    base = {
        "profile_completeness_score": 88.5,
        "signup_date": "2021-01-05",
        "last_active_date": "2026-06-01",
        "open_to_work_flag": True,
        "profile_views_received_30d": 12,
        "applications_submitted_30d": 3,
        "recruiter_response_rate": 0.42,
        "avg_response_time_hours": 6.5,
        "skill_assessment_scores": {"Python": 82.0, "SQL": 75.5},
        "connection_count": 320,
        "endorsements_received": 45,
        "notice_period_days": 30,
        "expected_salary_range_inr_lpa": {"min": 18.0, "max": 32.0},
        "preferred_work_mode": "hybrid",
        "willing_to_relocate": False,
        "github_activity_score": 64.0,
        "search_appearance_30d": 40,
        "saved_by_recruiters_30d": 5,
        "interview_completion_rate": 0.8,
        "offer_acceptance_rate": 0.5,
        "verified_email": True,
        "verified_phone": False,
        "linkedin_connected": True,
    }
    base.update(over)
    return base


def _candidate(cid: str, **over) -> dict:
    rec = {
        "candidate_id": cid,
        "profile": {
            "anonymized_name": "Test Candidate",
            "headline": "Backend Engineer",
            "summary": "Experienced engineer.",
            "location": "Bengaluru",
            "country": "India",
            "years_of_experience": 5.0,
            "current_title": "Senior Engineer",
            "current_company": "Acme",
            "current_company_size": "201-500",
            "current_industry": "Software",
        },
        "career_history": [
            _career("Acme", "Senior Engineer", "2022-01-01", None, "Led backend.")
        ],
        "education": [
            {
                "institution": "IIT",
                "degree": "B.Tech",
                "field_of_study": "CS",
                "start_year": 2014,
                "end_year": 2018,
                "grade": "8.5 CGPA",
                "tier": "tier_1",
            }
        ],
        "skills": [
            {"name": "Python", "proficiency": "expert", "endorsements": 30, "duration_months": 60},
            {"name": "JS", "proficiency": "advanced", "endorsements": 12, "duration_months": 24},
        ],
        "certifications": [{"name": "AWS SA", "issuer": "Amazon", "year": 2022}],
        "languages": [{"language": "English", "proficiency": "professional"}],
        "redrob_signals": _signals(),
    }
    rec.update(over)
    return rec


def build() -> list:
    rich_desc = (
        "Implemented   streaming   data pipelines on Kafka and Spark.\n\n"
        "Designed the schema-registry integration — watermark/state mgmt — "
        "and deduplication logic for late-arriving events.\tOwned on-call."
    )
    records = []

    # 0: clean valid record with messy whitespace to normalize.
    records.append(
        _candidate(
            "CAND_0000001",
            profile={
                "anonymized_name": "  Ira   Vora ",
                "headline": "Backend Engineer | SQL, Spark",
                "summary": "  Software / data professional.   Builds pipelines.  ",
                "location": "Toronto",
                "country": "Canada",
                "years_of_experience": 6.9,
                "current_title": "Backend Engineer",
                "current_company": "Mindtree",
                "current_company_size": "10001+",
                "current_industry": "IT Services",
            },
        )
    )

    # 1: record with a rich verbatim description + messy dates.
    rec = _candidate("CAND_0000002")
    rec["career_history"] = [
        _career("DataCorp", "Data Engineer", "March 8, 2024", None, rich_desc),
        _career("OldCo", "Analyst", "2019/07/03", "08-01-2024", "Built dashboards."),
    ]
    records.append(rec)

    # 2-6: plain valid records.
    for i in range(3, 8):
        records.append(_candidate(f"CAND_000000{i}"))

    # 7: duplicate of CAND_0000003 (kept-first; this one quarantined).
    records.append(_candidate("CAND_0000003", profile={
        "anonymized_name": "Dup", "headline": "x", "summary": "y", "location": "z",
        "country": "India", "years_of_experience": 1.0, "current_title": "Eng",
        "current_company": "C", "current_company_size": "1-10", "current_industry": "Soft",
    }))

    # 8: unknown pass-through field → schema_warning, still kept.
    rec = _candidate("CAND_0000008")
    rec["experimental_score"] = 0.99
    records.append(rec)

    # 9: missing required field (no redrob_signals) → quarantine.
    rec = _candidate("CAND_0000009")
    del rec["redrob_signals"]
    records.append(rec)

    # 10: bad candidate_id pattern → quarantine.
    records.append(_candidate("BADID_001"))

    # 11: unparseable date → null + warning, record still kept.
    rec = _candidate("CAND_0000011")
    rec["career_history"] = [
        _career("Z", "Eng", "not-a-date", None, "Worked.")
    ]
    records.append(rec)

    return records


def main() -> None:
    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in build()]
    # Insert a malformed JSON line in the middle (after the first two records).
    lines.insert(2, '{"candidate_id": "CAND_0000099", "profile": {bad json]')
    _FIXTURE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {_FIXTURE} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
