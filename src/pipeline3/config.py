"""Configuration for Pipeline 3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from src.pipeline1.config import Settings, load_settings


class RankingWeights(BaseModel):
    title_relevance: float = 0.25
    semantic_career: float = 0.20
    company: float = 0.10
    experience: float = 0.15
    skill: float = 0.15
    behavioral: float = 0.15


class HoneypotMultipliers(BaseModel):
    warning: float = 0.95
    suspicious: float = 0.80
    hard: float = 0.10


class HoneypotConfig(BaseModel):
    multipliers: HoneypotMultipliers = Field(default_factory=HoneypotMultipliers)
    flag_severity: dict[str, str] = Field(default_factory=dict)


class ExperienceConfig(BaseModel):
    job_hopping_months_threshold: int = 12
    ideal_tenure_months_min: int = 24
    ideal_tenure_months_max: int = 60


class BehavioralConfig(BaseModel):
    weights: dict[str, float] = Field(default_factory=dict)


class KeywordsConfig(BaseModel):
    target_roles: list[str] = Field(default_factory=list)


class Pipeline3Config(BaseModel):
    weights: RankingWeights = Field(default_factory=RankingWeights)
    honeypot: HoneypotConfig = Field(default_factory=HoneypotConfig)
    experience: ExperienceConfig = Field(default_factory=ExperienceConfig)
    behavioral: BehavioralConfig = Field(default_factory=BehavioralConfig)
    keywords: KeywordsConfig = Field(default_factory=KeywordsConfig)


class Pipeline3Settings:
    """Wrapper that holds both Pipeline 1 Settings and Pipeline 3 Config."""

    def __init__(self, p1_settings: Settings, p3_config: Pipeline3Config, taxonomy: dict[str, list[str]], job_description: str):
        self.p1 = p1_settings
        self.p3 = p3_config
        self.taxonomy = taxonomy
        self.job_description = job_description
        
        # Validate weights sum to 1.0 (with small float tolerance)
        total = sum([
            self.p3.weights.title_relevance,
            self.p3.weights.semantic_career,
            self.p3.weights.company,
            self.p3.weights.experience,
            self.p3.weights.skill,
            self.p3.weights.behavioral
        ])
        if abs(total - 1.0) > 1e-5:
            raise ValueError(f"Ranking weights must sum to 1.0, got {total}")


def load_pipeline3_settings(
    p1_config_path: str | Path = "config/settings.yaml",
    p3_config_path: str | Path = "config/ranking.yaml",
    taxonomy_path: str | Path = "config/skill_taxonomy.yaml",
    jd_path: str | Path = "config/job_description.txt",
) -> Pipeline3Settings:
    """Load all settings for Pipeline 3."""
    p1_settings = load_settings(p1_config_path)
    
    p3_path = Path(p3_config_path)
    p3_raw = yaml.safe_load(p3_path.read_text("utf-8")) or {}
    p3_config = Pipeline3Config(**p3_raw)
    
    tax_path = Path(taxonomy_path)
    tax_raw = yaml.safe_load(tax_path.read_text("utf-8")) or {}
    taxonomy = tax_raw.get("domains", {})
    
    # Casefold skills in taxonomy for easy matching
    for domain in taxonomy:
        taxonomy[domain] = [str(s).casefold() for s in taxonomy[domain]]
        
    jd_path = Path(jd_path)
    jd_text = jd_path.read_text("utf-8") if jd_path.exists() else ""
    
    return Pipeline3Settings(p1_settings, p3_config, taxonomy, jd_text)
