"""Integration tests: routing, determinism, verbatim, tamper, provenance."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from src.pipeline1.reporting.manifest import verify_manifest
from tests.conftest import FIXTURE, read_jsonl, run_pipeline


def _no_whitespace_nfkc(s: str) -> str:
    """Collapse to a whitespace/Unicode-insensitive canonical form."""
    return "".join(unicodedata.normalize("NFKC", s).split())


# -- routing: nothing silently dropped ------------------------------------

def test_routing_counts(run):
    summary = run["summary"]
    # 13 fixture lines: 1 malformed (parse error), 12 records processed.
    assert summary["records_processed"] == 12
    assert summary["parse_errors"] == 1
    # 2 quarantined (missing field, bad id), 1 duplicate, 9 written.
    assert summary["records_failed"] == 2
    assert summary["duplicates_removed"] == 1
    assert summary["records_written"] == 9
    assert len(run["transformed"]) == 9
    assert len(run["clean"]) == 9


def test_error_sinks_populated(run):
    err = run["tmp"] / "errors"
    parse = read_jsonl(err / "parse_errors.jsonl")
    invalid = read_jsonl(err / "invalid_records.jsonl")
    assert len(parse) == 1 and "line" in parse[0]
    statuses = {r["status"] for r in invalid}
    assert statuses == {"invalid", "duplicate"}
    dup = next(r for r in invalid if r["status"] == "duplicate")
    assert dup["duplicate_of"] == "CAND_0000003"


def test_transformed_contract(run):
    rec = next(r for r in run["transformed"] if r["candidate_id"] == "CAND_0000001")
    # flattened scalars
    assert rec["profile_years_of_experience"] == 6.9
    assert "redrob_github_activity_score" in rec
    # redrob_signals kept intact and separate from features
    assert "redrob_signals" in rec
    assert "skill_assessment_scores" in rec["redrob_signals"]
    assert "features" in rec and "skill_count" in rec["features"]
    # lineage + document + fingerprint present
    assert rec["_pipeline_metadata"] == {
        "validated": True,
        "cleaned": True,
        "quality_checked": True,
        "transformed": True,
        "feature_generated": True,
    }
    assert rec["candidate_document"]
    assert len(rec["candidate_fingerprint"]) == 64


def test_pass2_features_flags_and_report(run):
    rec = run["transformed"][0]
    # Pass 2 features present alongside Pass 1 ones.
    for key in (
        "total_career_months",
        "product_company_count",
        "consulting_company_count",
        "ai_skill_count",
        "expert_skill_count",
        "highest_education_tier",
    ):
        assert key in rec["features"]
    # Quality flags attached (kept records, list — possibly empty).
    assert isinstance(rec["quality_flags"], list)
    assert rec["_pipeline_metadata"]["quality_checked"] is True
    # quality_report.json produced with the expected shape.
    report = json.loads(
        (run["tmp"] / "transparency" / "quality_report.json").read_text("utf-8")
    )
    assert report["total_candidates_processed"] == len(run["transformed"])
    assert len(report["flag_counts"]) == 6


def test_candidate_document_is_pure_concatenation(run):
    rec = next(r for r in run["transformed"] if r["candidate_id"] == "CAND_0000001")
    doc = rec["candidate_document"]
    # Every part of the document must come from an existing source field.
    assert rec["profile_headline"] in doc
    assert rec["profile_summary"] in doc
    for ce in rec["career_history"]:
        assert ce["title"] in doc
        assert ce["description"] in doc


# -- verbatim preservation -------------------------------------------------

def test_descriptions_byte_preserved_except_whitespace_unicode():
    # Map source records by id (skip the malformed line which won't parse).
    src_by_id = {}
    for line in FIXTURE.read_text("utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        # Keep first occurrence to match the pipeline's keep-first dedup.
        src_by_id.setdefault(r.get("candidate_id"), r)

    import tempfile

    tmp = Path(tempfile.mkdtemp())
    run_pipeline(tmp)
    out = read_jsonl(tmp / "output" / "transformed_candidates.jsonl")

    for rec in out:
        src = src_by_id.get(rec["candidate_id"])
        if not src:
            continue
        for got, original in zip(rec["career_history"], src["career_history"]):
            assert _no_whitespace_nfkc(got["description"]) == _no_whitespace_nfkc(
                original["description"]
            )
        assert _no_whitespace_nfkc(rec["profile_summary"]) == _no_whitespace_nfkc(
            src["profile"]["summary"]
        )


# -- determinism / golden hashes ------------------------------------------

def test_determinism_identical_hashes_across_runs():
    import tempfile

    a = Path(tempfile.mkdtemp())
    b = Path(tempfile.mkdtemp())
    sa, _ = run_pipeline(a)
    sb, _ = run_pipeline(b)
    assert sa["clean_sha256"] == sb["clean_sha256"]
    assert sa["transformed_sha256"] == sb["transformed_sha256"]

    # The manifests also record identical output hashes.
    ma = json.loads((a / "output" / "manifest.json").read_text("utf-8"))
    mb = json.loads((b / "output" / "manifest.json").read_text("utf-8"))
    ha = {o["filename"]: o["sha256"] for o in ma["outputs"]}
    hb = {o["filename"]: o["sha256"] for o in mb["outputs"]}
    assert ha == hb


def test_fingerprint_stable_across_runs():
    import tempfile

    a = Path(tempfile.mkdtemp())
    b = Path(tempfile.mkdtemp())
    run_pipeline(a)
    run_pipeline(b)
    fa = {
        r["candidate_id"]: r["candidate_fingerprint"]
        for r in read_jsonl(a / "output" / "transformed_candidates.jsonl")
    }
    fb = {
        r["candidate_id"]: r["candidate_fingerprint"]
        for r in read_jsonl(b / "output" / "transformed_candidates.jsonl")
    }
    assert fa == fb


# -- provenance: verify pass / tamper fail --------------------------------

def test_verify_passes_on_untouched_outputs(run):
    manifest = run["tmp"] / "output" / "manifest.json"
    passed, results = verify_manifest(manifest, run["settings"].hmac_key())
    assert passed is True
    assert all(r["status"] == "PASS" for r in results)


def test_verify_fails_on_tampered_output(run):
    manifest = run["tmp"] / "output" / "manifest.json"
    target = run["tmp"] / "output" / "transformed_candidates.jsonl"
    target.write_bytes(target.read_bytes() + b'{"tampered":true}\n')
    passed, _ = verify_manifest(manifest, run["settings"].hmac_key())
    assert passed is False


def test_verify_fails_on_tampered_manifest(run):
    manifest = run["tmp"] / "output" / "manifest.json"
    data = json.loads(manifest.read_text("utf-8"))
    data["config_hash"] = "deadbeef"  # mutate signed body, keep old signature
    manifest.write_text(json.dumps(data), encoding="utf-8")
    passed, results = verify_manifest(manifest, run["settings"].hmac_key())
    assert passed is False
    assert any(r["check"] == "signature" and r["status"] == "FAIL" for r in results)
