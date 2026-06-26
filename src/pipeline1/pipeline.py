"""Pipeline orchestrator.

Composes the independent Steps into a single streaming pass over the input.
Records flow one at a time (never the whole file in RAM); the only unbounded
in-memory state is the dedup seen-id set and small running aggregates.

Routing per record:

* validation ``error``  → quarantine to ``invalid_records.jsonl`` +
  ``validation_errors.jsonl`` (status ``invalid``, reasons attached).
* cleaning duplicate    → quarantine to ``invalid_records.jsonl``
  (status ``duplicate``, ``duplicate_of``).
* otherwise             → cleaned record to ``clean_candidates.jsonl`` and the
  transformed/featurized/fingerprinted record to
  ``transformed_candidates.jsonl``.

Unexpected per-record exceptions are captured to ``processing_errors.jsonl``
with a traceback and the run continues — nothing is silently dropped.
"""

from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Any

from src.pipeline1.cleaning.step import CleaningStep
from src.pipeline1.config import Settings
from src.pipeline1.feature_generation.step import FeatureGenerationStep
from src.pipeline1.ingestion.reader import JsonlReader
from src.pipeline1.integrity.step import IntegrityStep
from src.pipeline1.reporting.manifest import build_manifest, write_manifest
from src.pipeline1.reporting.writers import JsonlWriter, write_report
from src.pipeline1.transformation.step import TransformationStep
from src.pipeline1.validation.quality_flags import QualityFlagStep
from src.pipeline1.validation.step import ValidationStep
from src.utils.integrity import candidate_fingerprint, sha256_file, write_sidecar
from src.utils.logging import setup_logging


class Pipeline:
    """Streaming Pipeline 0 + 1 orchestrator."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = setup_logging(
            settings.paths.logs_dir,
            level=settings.logging.level,
            pipeline_log=settings.logging.pipeline_log,
            errors_log=settings.logging.errors_log,
        )
        self.validation = ValidationStep()
        self.cleaning = CleaningStep(settings)
        self.quality = QualityFlagStep(settings.quality_thresholds)
        self.transformation = TransformationStep(settings)
        self.features = FeatureGenerationStep(settings.registries)
        self.integrity = IntegrityStep()

    def run(self, input_path: str | Path) -> dict[str, Any]:
        """Execute the full pipeline over ``input_path``.

        Returns:
            A run summary dict (counts, timings, output hashes).
        """
        start = time.perf_counter()
        s = self.settings
        out_dir = Path(s.paths.output_dir)
        err_dir = Path(s.paths.errors_dir)
        trans_dir = Path(s.paths.transparency_dir)
        for d in (out_dir, err_dir, trans_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.logger.info("Pipeline 1 starting | input=%s", input_path)
        self.logger.info("Hashing input artifact for lineage…")
        input_sha256 = sha256_file(input_path)
        self.logger.info("input sha256=%s", input_sha256)

        # Error sinks.
        parse_err = JsonlWriter(err_dir / "parse_errors.jsonl")
        invalid = JsonlWriter(err_dir / "invalid_records.jsonl")
        val_err = JsonlWriter(err_dir / "validation_errors.jsonl")
        proc_err = JsonlWriter(err_dir / "processing_errors.jsonl")
        # Data outputs.
        clean_out = JsonlWriter(out_dir / "clean_candidates.jsonl")
        trans_out = JsonlWriter(out_dir / "transformed_candidates.jsonl")

        def on_parse_error(line_no: int, snippet: str, error: str) -> None:
            parse_err.write({"line": line_no, "error": error, "raw": snippet})

        reader = JsonlReader(input_path, on_parse_error=on_parse_error)

        records_in = 0
        records_failed = 0
        duplicates = 0
        written = 0
        batch = s.batch_size

        try:
            for line_no, raw in reader:
                records_in += 1
                try:
                    routed = self._process_one(
                        raw, line_no, clean_out, trans_out, invalid, val_err
                    )
                    if routed == "written":
                        written += 1
                    elif routed == "failed":
                        records_failed += 1
                    elif routed == "duplicate":
                        duplicates += 1
                except Exception:  # noqa: BLE001 - never let one record abort run
                    records_failed += 1
                    cid = raw.get("candidate_id") if isinstance(raw, dict) else None
                    proc_err.write(
                        {
                            "line": line_no,
                            "candidate_id": cid,
                            "status": "processing_error",
                            "traceback": traceback.format_exc(),
                        }
                    )
                    self.logger.error(
                        "processing error at line %s (cid=%s)", line_no, cid,
                        exc_info=True,
                    )

                if records_in % batch == 0:
                    self.logger.info(
                        "progress: in=%d written=%d failed=%d dup=%d",
                        records_in, written, records_failed, duplicates,
                    )
        finally:
            for w in (parse_err, invalid, val_err, proc_err, clean_out, trans_out):
                w.close()

        elapsed = round(time.perf_counter() - start, 3)

        # File hashes + sidecars for the deterministic data outputs.
        clean_sha = write_sidecar(clean_out.path)
        trans_sha = write_sidecar(trans_out.path)

        outputs = [
            {
                "filename": clean_out.path.name,
                "sha256": clean_sha,
                "row_count": clean_out.rows,
                "stage": "cleaning",
            },
            {
                "filename": trans_out.path.name,
                "sha256": trans_sha,
                "row_count": trans_out.rows,
                "stage": "transformation",
            },
        ]
        manifest = build_manifest(
            outputs=outputs,
            input_path=str(input_path),
            input_sha256=input_sha256,
            config_hash=s.config_hash,
            hmac_key=s.hmac_key(),
        )
        write_manifest(out_dir / "manifest.json", manifest)

        self._write_reports(
            trans_dir,
            records_in=records_in,
            records_failed=records_failed,
            duplicates=duplicates,
            written=written,
            elapsed=elapsed,
        )

        summary = {
            "records_processed": records_in,
            "records_written": written,
            "records_failed": records_failed,
            "duplicates_removed": duplicates,
            "parse_errors": reader.parse_errors,
            "processing_time": elapsed,
            "clean_sha256": clean_sha,
            "transformed_sha256": trans_sha,
        }
        self.logger.info("Pipeline 1 complete | %s", summary)
        return summary

    # -- per-record routing ----------------------------------------------

    def _process_one(
        self,
        raw: dict[str, Any],
        line_no: int,
        clean_out: JsonlWriter,
        trans_out: JsonlWriter,
        invalid: JsonlWriter,
        val_err: JsonlWriter,
    ) -> str:
        """Route one raw record; return 'written' | 'failed' | 'duplicate'."""
        vr = self.validation.process(raw, line_no)
        if vr.status == "error":
            reason = "; ".join(i["message"] for i in vr.issues) or "schema validation failed"
            invalid.write(
                {
                    "candidate_id": vr.candidate_id,
                    "line": line_no,
                    "status": "invalid",
                    "reason": reason,
                    "record": raw,
                }
            )
            val_err.write(
                {
                    "candidate_id": vr.candidate_id,
                    "line": line_no,
                    "issues": vr.issues,
                }
            )
            return "failed"

        cr = self.cleaning.process(vr.record)
        if cr.is_duplicate:
            invalid.write(
                {
                    "candidate_id": vr.candidate_id,
                    "line": line_no,
                    "status": "duplicate",
                    "duplicate_of": cr.duplicate_of,
                }
            )
            return "duplicate"

        warning = [i["message"] for i in vr.issues] if vr.status == "warning" else None

        # Quality flags (after cleaning, before transformation). Records are kept;
        # the flags are appended to the shared record so both outputs carry them.
        self.quality.process(cr.record)

        # clean_candidates.jsonl — cleaned nested record + lineage + fingerprint.
        clean_record = dict(cr.record)
        clean_record["_pipeline_metadata"] = {
            "validated": True,
            "cleaned": True,
            "quality_checked": True,
            "transformed": False,
            "feature_generated": False,
        }
        if warning:
            clean_record["schema_warning"] = warning
        clean_record["candidate_fingerprint"] = candidate_fingerprint(clean_record)
        clean_out.write(clean_record)

        # transformed_candidates.jsonl — flatten + features + fingerprint.
        transformed = self.transformation.process(cr.record)
        if warning:
            transformed["schema_warning"] = warning
        transformed = self.features.process(transformed)
        transformed = self.integrity.process(transformed)
        trans_out.write(transformed)

        return "written"

    # -- reports ----------------------------------------------------------

    def _write_reports(
        self,
        trans_dir: Path,
        records_in: int,
        records_failed: int,
        duplicates: int,
        written: int,
        elapsed: float,
    ) -> None:
        v = self.validation.report()
        c = self.cleaning.report()
        t = self.transformation.report()
        f = self.features.report()
        ig = self.integrity.report()

        write_report(trans_dir / "quality_report.json", self.quality.report())

        write_report(
            trans_dir / "validation_report.json",
            {
                "records_processed": records_in,
                "records_failed": records_failed,
                **v,
                "processing_time": elapsed,
            },
        )
        write_report(
            trans_dir / "cleaning_report.json",
            {
                "records_processed": records_in,
                "duplicates_removed": duplicates,
                **c,
                "processing_time": elapsed,
            },
        )
        write_report(
            trans_dir / "transformation_report.json",
            {
                "records_processed": records_in,
                "records_written": written,
                **t,
                **f,
                **ig,
                "processing_time": elapsed,
            },
        )
