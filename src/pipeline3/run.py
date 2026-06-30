"""Command-line entry point for Pipeline 3."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.pipeline3.config import load_pipeline3_settings
from src.pipeline3.pipeline import Pipeline3


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redrob-pipeline3", description="Redrob Pipeline 3 (Hybrid Ranking + Explainability)"
    )
    
    parser.add_argument("--input", default="output/transformed_candidates.jsonl", help="path to transformed input")
    parser.add_argument("--config-p1", default="config/settings.yaml")
    parser.add_argument("--config-p3", default="config/ranking.yaml")
    parser.add_argument("--taxonomy", default="config/skill_taxonomy.yaml")
    parser.add_argument("--jd", default="config/job_description.txt")
    parser.add_argument("--top-n", type=int, default=100, help="Only output the top N candidates (default: 100). Use 0 for all.")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    args = _build_parser().parse_args(argv)

    try:
        settings = load_pipeline3_settings(
            p1_config_path=args.config_p1,
            p3_config_path=args.config_p3,
            taxonomy_path=args.taxonomy,
            jd_path=args.jd
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"FATAL: cannot load config: {exc}", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"FATAL: input not found: {input_path}", file=sys.stderr)
        return 2
        
    try:
        top_n = args.top_n if args.top_n > 0 else None
        summary = Pipeline3(settings).run(input_path, top_n=top_n)
    except (OSError, ValueError) as exc:
        print(f"FATAL: pipeline error: {exc}", file=sys.stderr)
        return 1
        
    print("RUN COMPLETE:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
