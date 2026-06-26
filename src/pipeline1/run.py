"""Command-line entry point for Pipeline 0 + 1.

Usage::

    python -m src.pipeline1.run --input data/candidates.jsonl --config config/settings.yaml
    python -m src.pipeline1.run verify --manifest output/manifest.json --config config/settings.yaml

The ``run`` subcommand is the default, so the first form (no subcommand) works.
Exits non-zero on fatal IO/config errors or on a failed ``verify``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.pipeline1.config import load_settings
from src.pipeline1.pipeline import Pipeline
from src.pipeline1.reporting.manifest import verify_manifest

_DEFAULT_CONFIG = "config/settings.yaml"
_SUBCOMMANDS = {"run", "verify"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redrob-pipeline1", description="Redrob Pipeline 0 + 1 (Pass 1)"
    )
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="run the preprocessing pipeline")
    run_p.add_argument("--input", help="path to .jsonl or .jsonl.gz input")
    run_p.add_argument("--config", default=_DEFAULT_CONFIG)

    verify_p = sub.add_parser("verify", help="verify outputs against a manifest")
    verify_p.add_argument("--manifest", required=True)
    verify_p.add_argument("--config", default=_DEFAULT_CONFIG)

    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    """Default to the ``run`` subcommand when none is given."""
    if not argv or argv[0] not in _SUBCOMMANDS:
        return ["run", *argv]
    return argv


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    argv = _normalize_argv(list(sys.argv[1:] if argv is None else argv))
    args = _build_parser().parse_args(argv)

    try:
        settings = load_settings(args.config)
    except (FileNotFoundError, OSError) as exc:
        print(f"FATAL: cannot load config {args.config!r}: {exc}", file=sys.stderr)
        return 2

    if args.command == "verify":
        passed, results = verify_manifest(args.manifest, settings.hmac_key())
        for r in results:
            print(f"[{r['status']}] {r['check']}")
        print("VERIFY:", "PASS" if passed else "FAIL")
        return 0 if passed else 1

    # run
    input_path = args.input or settings.paths.input
    if not Path(input_path).exists():
        print(f"FATAL: input not found: {input_path}", file=sys.stderr)
        return 2
    try:
        summary = Pipeline(settings).run(input_path)
    except (OSError, ValueError) as exc:
        print(f"FATAL: pipeline error: {exc}", file=sys.stderr)
        return 1
    print("RUN COMPLETE:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
