"""Tests for Pipeline 3."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline3.config import load_pipeline3_settings
from src.pipeline3.pipeline import Pipeline3

from tests.conftest import FIXTURE, run_pipeline

ROOT = Path(__file__).resolve().parents[1]
P1_CONFIG = ROOT / "config" / "settings.yaml"
P3_CONFIG = ROOT / "config" / "ranking.yaml"
TAXONOMY = ROOT / "config" / "skill_taxonomy.yaml"
JD = ROOT / "config" / "job_description.txt"

@pytest.fixture
def p3_settings(tmp_path):
    s = load_pipeline3_settings(
        p1_config_path=P1_CONFIG,
        p3_config_path=P3_CONFIG,
        taxonomy_path=TAXONOMY,
        jd_path=JD
    )
    s.p1.paths.output_dir = str(tmp_path / "output")
    s.p1.paths.transparency_dir = str(tmp_path / "transparency")
    s.p1.paths.logs_dir = str(tmp_path / "logs")
    s.p1.paths.errors_dir = str(tmp_path / "errors")
    return s

def test_pipeline3_end_to_end(tmp_path, p3_settings):
    # 1. Run Pipeline 1 to get transformed_candidates.jsonl
    p1_summary, _ = run_pipeline(tmp_path)
    assert p1_summary["records_written"] > 0
    
    transformed_path = tmp_path / "output" / "transformed_candidates.jsonl"
    assert transformed_path.exists()
    
    # 2. Run Pipeline 3
    p3 = Pipeline3(p3_settings)
    p3_summary = p3.run(transformed_path)
    
    # Pipeline 1 writes 9 candidates for the fixture, so P3 should process 9
    assert p3_summary["records_processed"] == 9
    
    # 3. Verify outputs
    out_dir = tmp_path / "output"
    trans_dir = tmp_path / "transparency"
    
    assert (out_dir / "ranked_candidates.json").exists()
    assert (out_dir / "ranked_candidates.csv").exists()
    assert (out_dir / "honeypot_history.json").exists()
    assert (out_dir / "unknown_skills_report.json").exists()
    assert (trans_dir / "ranking_report.json").exists()
    
    # 4. Check contents of JSON
    with open(out_dir / "ranked_candidates.json", encoding="utf-8") as f:
        ranked = json.load(f)
        
    assert len(ranked) == 9
    
    # Check explainability structure of top candidate
    top = ranked[0]
    assert "rank" in top
    assert top["rank"] == 1
    assert "score_breakdown" in top
    assert "strengths" in top
    assert "weaknesses" in top
    assert "penalties" in top
    assert "confidence_score" in top
    assert "candidate_domain" in top
    assert "reasoning" in top
    
    # Scores must be between 0 and 1
    for score in top["score_breakdown"].values():
        assert 0.0 <= score <= 1.0

def test_determinism_across_runs(tmp_path):
    # Run P1 once, put it in a common place
    p1_tmp = tmp_path / "p1"
    run_pipeline(p1_tmp)
    transformed_path = p1_tmp / "output" / "transformed_candidates.jsonl"
    
    # Run P3 twice in different output dirs
    a_dir = tmp_path / "a"
    a_dir.mkdir()
    s_a = load_pipeline3_settings(p1_config_path=P1_CONFIG, p3_config_path=P3_CONFIG, taxonomy_path=TAXONOMY, jd_path=JD)
    s_a.p1.paths.output_dir = str(a_dir / "output")
    s_a.p1.paths.transparency_dir = str(a_dir / "transparency")
    s_a.p1.paths.logs_dir = str(a_dir / "logs")
    s_a.p1.paths.errors_dir = str(a_dir / "errors")
    
    Pipeline3(s_a).run(transformed_path)
    
    b_dir = tmp_path / "b"
    b_dir.mkdir()
    s_b = load_pipeline3_settings(p1_config_path=P1_CONFIG, p3_config_path=P3_CONFIG, taxonomy_path=TAXONOMY, jd_path=JD)
    s_b.p1.paths.output_dir = str(b_dir / "output")
    s_b.p1.paths.transparency_dir = str(b_dir / "transparency")
    s_b.p1.paths.logs_dir = str(b_dir / "logs")
    s_b.p1.paths.errors_dir = str(b_dir / "errors")
    
    Pipeline3(s_b).run(transformed_path)
    
    # Compare outputs byte for byte (csv and json)
    a_csv = (a_dir / "output" / "ranked_candidates.csv").read_bytes()
    b_csv = (b_dir / "output" / "ranked_candidates.csv").read_bytes()
    assert a_csv == b_csv
    
    a_json = (a_dir / "output" / "ranked_candidates.json").read_bytes()
    b_json = (b_dir / "output" / "ranked_candidates.json").read_bytes()
    assert a_json == b_json
