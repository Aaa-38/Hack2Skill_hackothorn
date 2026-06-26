"""Shared pytest fixtures.

Provides a helper to run the full pipeline into an isolated temp directory using
the real config but redirected output/transparency/logs/errors paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.pipeline1.config import Settings, load_settings
from src.pipeline1.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sample.jsonl"
CONFIG = ROOT / "config" / "settings.yaml"


def _settings_for(tmp: Path) -> Settings:
    s = load_settings(CONFIG)
    s.paths.output_dir = str(tmp / "output")
    s.paths.transparency_dir = str(tmp / "transparency")
    s.paths.logs_dir = str(tmp / "logs")
    s.paths.errors_dir = str(tmp / "errors")
    return s


def run_pipeline(tmp: Path) -> tuple[dict[str, Any], Settings]:
    """Run the pipeline on the fixture into ``tmp`` and return (summary, settings)."""
    s = _settings_for(tmp)
    summary = Pipeline(s).run(str(FIXTURE))
    return summary, s


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


@pytest.fixture
def run(tmp_path: Path):
    summary, settings = run_pipeline(tmp_path)
    return {
        "summary": summary,
        "settings": settings,
        "tmp": tmp_path,
        "clean": read_jsonl(tmp_path / "output" / "clean_candidates.jsonl"),
        "transformed": read_jsonl(
            tmp_path / "output" / "transformed_candidates.jsonl"
        ),
    }
