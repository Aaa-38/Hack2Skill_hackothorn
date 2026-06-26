"""Typed configuration loaded from YAML via pydantic-settings.

All paths, mappings, defaults and thresholds live in ``config/settings.yaml``
and ``config/skill_mappings.yaml`` — nothing is hardcoded in the source. The
config hash (over the canonical merged config) is recorded in the manifest so a
run is fully reproducible from input + code + config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, PrivateAttr

from src.utils.canonical import canonical_bytes
from src.utils.integrity import sha256_bytes


class PathsConfig(BaseModel):
    input: str
    output_dir: str
    transparency_dir: str
    logs_dir: str
    errors_dir: str
    skill_mappings: str
    # Pass 2 classification registries.
    consulting_companies: str = "config/consulting_companies.yaml"
    product_companies: str = "config/product_companies.yaml"
    ai_native_companies: str = "config/ai_native_companies.yaml"
    ai_skills: str = "config/ai_skills.yaml"


class QualityThresholds(BaseModel):
    """Configurable thresholds for the Pass 2 quality flags."""

    impossible_tenure_factor: float = 1.5
    impossible_tenure_buffer_months: int = 24
    expert_zero_experience_min_skills: int = 5
    # Fixed reference date keeps the future_dates flag deterministic.
    reference_date: str = "2026-06-25"


@dataclass(frozen=True)
class Registries:
    """Casefolded classification lookups shared with Pipeline 3."""

    consulting: frozenset[str]
    product: frozenset[str]
    ai_native: frozenset[str]
    ai_skills: frozenset[str]


class CleaningConfig(BaseModel):
    defaults: dict[str, Any] = Field(default_factory=dict)
    verbatim_fields: list[str] = Field(default_factory=list)
    date_fields: list[str] = Field(default_factory=list)


class TransformationConfig(BaseModel):
    flatten: dict[str, str] = Field(default_factory=dict)
    preserve_lists: list[str] = Field(default_factory=list)
    document_separator: str = "\n"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    pipeline_log: str = "pipeline.log"
    errors_log: str = "errors.log"


class IntegrityConfig(BaseModel):
    hash_algorithm: str = "sha256"
    hmac_key_env: str = "REDROB_HMAC_KEY"
    hmac_key_fallback: str = "redrob-pipeline1-dev-signing-key"


class Settings(BaseModel):
    """Root settings object plus derived helpers."""

    paths: PathsConfig
    batch_size: int = 5000
    cleaning: CleaningConfig = Field(default_factory=CleaningConfig)
    transformation: TransformationConfig = Field(default_factory=TransformationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    integrity: IntegrityConfig = Field(default_factory=IntegrityConfig)
    quality_thresholds: QualityThresholds = Field(default_factory=QualityThresholds)

    # Hash of the raw config document, used in the manifest for reproducibility.
    config_hash: str = ""

    _skill_cache: dict[str, str] | None = PrivateAttr(default=None)
    _registry_cache: "Registries | None" = PrivateAttr(default=None)

    def hmac_key(self) -> str:
        """Resolve the HMAC signing key from the environment or the fallback."""
        return os.environ.get(
            self.integrity.hmac_key_env, self.integrity.hmac_key_fallback
        )

    @property
    def skill_mappings(self) -> dict[str, str]:
        """Load and cache the lowercased skill-alias map."""
        if self._skill_cache is None:
            raw = yaml.safe_load(Path(self.paths.skill_mappings).read_text("utf-8"))
            mappings = (raw or {}).get("mappings", {}) if isinstance(raw, dict) else {}
            self._skill_cache = {str(k).casefold(): str(v) for k, v in mappings.items()}
        return self._skill_cache

    @property
    def registries(self) -> Registries:
        """Load and cache the casefolded classification registries (Pass 2)."""
        if self._registry_cache is None:
            self._registry_cache = Registries(
                consulting=_load_names(self.paths.consulting_companies, "companies"),
                product=_load_names(self.paths.product_companies, "companies"),
                ai_native=_load_names(self.paths.ai_native_companies, "companies"),
                ai_skills=_load_names(self.paths.ai_skills, "skills"),
            )
        return self._registry_cache


def _load_names(path: str | Path, key: str) -> frozenset[str]:
    """Load a YAML list under ``key`` and return casefolded, stripped names."""
    raw = yaml.safe_load(Path(path).read_text("utf-8"))
    items = (raw or {}).get(key, []) if isinstance(raw, dict) else []
    return frozenset(str(item).strip().casefold() for item in items)


def load_settings(config_path: str | Path) -> Settings:
    """Load :class:`Settings` from a YAML file and compute its config hash.

    Args:
        config_path: Path to ``settings.yaml``.

    Returns:
        A fully populated :class:`Settings`.

    Raises:
        FileNotFoundError: If the config file does not exist.
    """
    config_path = Path(config_path)
    raw = yaml.safe_load(config_path.read_text("utf-8")) or {}
    config_hash = sha256_bytes(canonical_bytes(raw))
    settings = Settings(**raw)
    settings.config_hash = config_hash
    return settings
