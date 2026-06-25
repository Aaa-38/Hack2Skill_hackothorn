"""Pass 2: registry loading and case-insensitive lookup."""

from __future__ import annotations

from tests.conftest import CONFIG
from src.pipeline1.config import load_settings


def test_all_four_registries_load():
    reg = load_settings(CONFIG).registries
    assert len(reg.consulting) == 12
    assert len(reg.product) == 21
    assert len(reg.ai_native) == 10
    assert len(reg.ai_skills) == 19


def test_company_lookup_is_case_insensitive():
    reg = load_settings(CONFIG).registries
    # Registry entries are stored casefolded; match regardless of input casing.
    assert "tcs" in reg.consulting
    assert "TCS".strip().casefold() in reg.consulting
    assert "swiggy" in reg.product
    assert "SwIgGy".strip().casefold() in reg.product
    assert "sarvam ai" in reg.ai_native
    assert "nlp" in reg.ai_skills
