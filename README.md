# Intelligent Candidate Discovery & Ranking Pipeline

This repository contains the data processing pipelines for the Intelligent Candidate Discovery & Ranking Challenge.

## Architecture

The system is broken down into three decoupled pipelines:

### Pipeline 1: Ingestion & Verification
Performs initial validation, schema verification, data cleaning (whitespace removal, unicode normalization), and basic text transformation. It also normalizes skills against the config map.
- **Outputs**: `clean_candidates.jsonl`, `transformed_candidates.jsonl`, `errors/*`

### Pipeline 2: Feature Generation & Quality
Enhances candidate records by computing statistical features and applying quality heuristics (flagging impossible tenures, overlapping roles, future dates, etc.). Reuses output schemas from Pipeline 1.
- **Outputs**: Features added to `transformed_candidates.jsonl`, `quality_report.json`

### Pipeline 3: Hybrid Ranking & Explainability Engine
Estimates candidate confidence and domain relevance without discarding candidates. Features a 3-tier honeypot engine that maps quality flags to score multipliers. Deterministic and CPU-only.
- **Outputs**: `ranked_candidates.csv`, `ranked_candidates.json`, `honeypot_history.json`, `ranking_report.json`, `unknown_skills_report.json`

## Setup

```bash
pip install -r requirements.txt
# Requirements: pydantic, pyyaml
```

## Running Pipelines

**Run Pipeline 1 & 2** (orchestrated together):
```bash
python -m src.pipeline1.run --input data/sample_candidates.jsonl
```

**Run Pipeline 3**:
```bash
# Requires Pipeline 1 & 2 to run first
python -m src.pipeline3.run --input output/transformed_candidates.jsonl
```

## Configuration

Configuration is managed via YAML files in the `config/` directory:
- `settings.yaml`: Paths and behavior for pipelines 1 & 2
- `ranking.yaml`: Scoring weights, honeypot multipliers, and behavioral thresholds for Pipeline 3
- `skill_mappings.yaml`: Canonical skill names for Pipeline 1
- `skill_taxonomy.yaml`: Domain categorizations for skills in Pipeline 3

## Tests

```bash
python -m pytest tests/ -v
```
