"""Logging configuration from settings.

Two file sinks plus a console sink are wired up:

* ``logs/pipeline.log`` — INFO and above (lifecycle, counts, per-stage timing).
* ``logs/errors.log`` — ERROR and above (exceptions with traceback).

Log records carry timestamps and live only in log files / manifests — never in
data records — so the data outputs stay deterministic.
"""

from __future__ import annotations

import logging
from pathlib import Path

_CONFIGURED = False


def setup_logging(
    logs_dir: str | Path,
    level: str = "INFO",
    pipeline_log: str = "pipeline.log",
    errors_log: str = "errors.log",
) -> logging.Logger:
    """Configure and return the root ``redrob`` logger.

    Idempotent: repeated calls do not stack duplicate handlers.

    Args:
        logs_dir: Directory that will hold the log files (created if missing).
        level: Minimum level for the pipeline log and console.
        pipeline_log: Filename for the INFO+ log.
        errors_log: Filename for the ERROR+ log.

    Returns:
        The configured ``redrob`` logger.
    """
    global _CONFIGURED
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("redrob")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if _CONFIGURED:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    pipeline_handler = logging.FileHandler(logs_dir / pipeline_log, encoding="utf-8")
    pipeline_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    pipeline_handler.setFormatter(fmt)

    error_handler = logging.FileHandler(logs_dir / errors_log, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)

    console = logging.StreamHandler()
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(fmt)

    logger.addHandler(pipeline_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console)

    _CONFIGURED = True
    return logger
