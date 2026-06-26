"""Pass 2: extended features (counts/lookups only, no scores)."""

from __future__ import annotations

from src.pipeline1.config import load_settings
from src.pipeline1.feature_generation.step import FeatureGenerationStep
from tests.conftest import CONFIG

_REG = load_settings(CONFIG).registries


def _features(record: dict) -> dict:
    return FeatureGenerationStep(_REG).process(record)["features"]


def test_product_company_count():
    rec = {"career_history": [{"company": "Swiggy"}, {"company": "Acme"}]}
    assert _features(rec)["product_company_count"] == 1


def test_consulting_company_count_case_insensitive():
    rec = {"career_history": [{"company": "tcs"}, {"company": "INFOSYS"}]}
    assert _features(rec)["consulting_company_count"] == 2


def test_expert_skill_count():
    rec = {
        "skills": [
            {"name": "a", "proficiency": "expert"},
            {"name": "b", "proficiency": "expert"},
            {"name": "c", "proficiency": "expert"},
            {"name": "d", "proficiency": "advanced"},
        ]
    }
    assert _features(rec)["expert_skill_count"] == 3


def test_ai_skill_count_uses_normalized_name():
    rec = {
        "skills": [
            {"name": "PyTorch", "normalized_name": "pytorch"},
            {"name": "NLP", "normalized_name": "nlp"},
            {"name": "Excel", "normalized_name": "excel"},
        ]
    }
    assert _features(rec)["ai_skill_count"] == 2


def test_total_career_months_and_highest_tier():
    rec = {
        "career_history": [{"duration_months": 12}, {"duration_months": 30}],
        "education": [{"tier": "tier_3"}, {"tier": "tier_1"}, {"tier": "unknown"}],
    }
    f = _features(rec)
    assert f["total_career_months"] == 42
    assert f["highest_education_tier"] == "tier_1"


def test_highest_tier_unknown_when_no_education():
    assert _features({})["highest_education_tier"] == "unknown"


def test_no_scores_or_weights_in_features():
    f = _features({"skills": [], "career_history": [], "education": []})
    assert not any(k for k in f if "score" in k or "weight" in k or "rank" in k)
