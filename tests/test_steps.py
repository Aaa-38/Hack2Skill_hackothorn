"""Unit tests for each independent Step."""

from __future__ import annotations

from src.pipeline1.cleaning.skill_normalizer import SkillNormalizer
from src.pipeline1.cleaning.step import _normalize_strings, _to_iso_date
from src.pipeline1.cleaning.text import normalize_key, normalize_text
from src.pipeline1.config import Registries
from src.pipeline1.feature_generation.step import FeatureGenerationStep
from src.pipeline1.integrity.step import IntegrityStep
from src.pipeline1.validation.step import ValidationStep

_EMPTY_REGISTRIES = Registries(
    consulting=frozenset(),
    product=frozenset(),
    ai_native=frozenset(),
    ai_skills=frozenset(),
)


def _valid_record() -> dict:
    return {
        "candidate_id": "CAND_1234567",
        "profile": {
            "anonymized_name": "A",
            "headline": "H",
            "summary": "S",
            "location": "L",
            "country": "C",
            "years_of_experience": 3.0,
            "current_title": "T",
            "current_company": "Co",
            "current_company_size": "1-10",
            "current_industry": "I",
        },
        "career_history": [
            {
                "company": "Co",
                "title": "T",
                "start_date": "2020-01-01",
                "end_date": None,
                "duration_months": 12,
                "is_current": True,
                "industry": "I",
                "company_size": "1-10",
                "description": "D",
            }
        ],
        "education": [],
        "skills": [{"name": "Python", "proficiency": "expert", "endorsements": 5}],
        "redrob_signals": {
            "profile_completeness_score": 50.0,
            "last_active_date": "2026-01-01",
            "open_to_work_flag": True,
            "recruiter_response_rate": 0.5,
            "notice_period_days": 30,
            "willing_to_relocate": False,
            "github_activity_score": 10.0,
            "saved_by_recruiters_30d": 1,
            "interview_completion_rate": 0.5,
            "offer_acceptance_rate": 0.5,
            "verified_email": True,
            "verified_phone": False,
        },
    }


# -- validation -----------------------------------------------------------

def test_validation_valid():
    res = ValidationStep().process(_valid_record(), 1)
    assert res.status == "valid"


def test_validation_missing_required_quarantines():
    rec = _valid_record()
    del rec["redrob_signals"]
    res = ValidationStep().process(rec, 7)
    assert res.status == "error"
    assert any("redrob_signals" in i["location"] for i in res.issues)


def test_validation_bad_id_quarantines():
    rec = _valid_record()
    rec["candidate_id"] = "NOPE"
    assert ValidationStep().process(rec, 1).status == "error"


def test_validation_extra_field_is_warning():
    rec = _valid_record()
    rec["surprise"] = 1
    res = ValidationStep().process(rec, 1)
    assert res.status == "warning"
    assert "surprise" in res.issues[0]["message"]


# -- text / dates ---------------------------------------------------------

def test_normalize_text_whitespace_and_unicode():
    assert normalize_text("  a   b\tc  ") == "a b c"
    # NFKC folds the ligature ﬁ -> fi
    assert normalize_text("ﬁle") == "file"


def test_normalize_key_casefolds():
    assert normalize_key("  Java Script ") == "java script"


def test_to_iso_date():
    assert _to_iso_date("March 8, 2024") == "2024-03-08"
    assert _to_iso_date("2019/07/03") == "2019-07-03"
    assert _to_iso_date("not-a-date") is None
    assert _to_iso_date(None) is None


def test_normalize_strings_recurses_in_place():
    obj = {"a": "  x  y ", "b": [{"c": " z "}]}
    _normalize_strings(obj)
    assert obj == {"a": "x y", "b": [{"c": "z"}]}


# -- skill normalizer -----------------------------------------------------

def test_skill_normalizer_maps_and_preserves_name():
    sn = SkillNormalizer({"js": "javascript"})
    out = sn.normalize({"name": "JS", "endorsements": 3})
    assert out["name"] == "JS"  # preserved
    assert out["normalized_name"] == "javascript"


def test_skill_normalizer_fallback_casefold():
    sn = SkillNormalizer({})
    assert sn.normalize({"name": "Rust"})["normalized_name"] == "rust"


# -- features (counts only, no scores) ------------------------------------

def test_feature_generation_counts():
    rec = {
        "skills": [
            {"name": "a", "endorsements": 3, "duration_months": 10},
            {"name": "b", "endorsements": 7, "duration_months": 20},
        ],
        "certifications": [{"name": "c"}],
        "languages": [{"language": "en"}],
        "career_history": [{"title": "t"}],
        "_pipeline_metadata": {"feature_generated": False},
    }
    out = FeatureGenerationStep(_EMPTY_REGISTRIES).process(rec)
    f = out["features"]
    assert f["skill_count"] == 2
    assert f["total_endorsements"] == 10
    assert f["average_skill_duration"] == 15.0
    assert f["certification_count"] == 1
    assert out["_pipeline_metadata"]["feature_generated"] is True
    # No ranking/score keys leak in.
    assert not any("score" in k or "rank" in k for k in f)


# -- integrity ------------------------------------------------------------

def test_integrity_fingerprint_excludes_itself_and_is_stable():
    rec = {"candidate_id": "CAND_0000001", "x": 1}
    out = IntegrityStep().process(dict(rec))
    fp = out["candidate_fingerprint"]
    # Re-fingerprinting the stamped record yields the same value.
    again = IntegrityStep().process(dict(out))
    assert again["candidate_fingerprint"] == fp
