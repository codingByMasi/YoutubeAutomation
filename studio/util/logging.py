"""Logging setup with secret redaction."""

from __future__ import annotations

import logging
from pathlib import Path

_LOGGER_NAME = "studio"


class RedactSecrets(logging.Filter):
    """Replace any known secret value in log records with '***'."""

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self.secrets = [s for s in secrets if s and len(s) >= 4]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for s in self.secrets:
            msg = msg.replace(s, "***")
        record.msg, record.args = msg, ()
        return True


def setup_logging(log_dir: Path, secrets: list[str], verbose: bool = False) -> logging.Logger:
    """Log to logs/studio.log (always) and stderr (warnings, or everything with verbose)."""
    logger = logging.getLogger(_LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    redact = RedactSecrets(secrets)
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_dir / "studio.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    fh.addFilter(redact)
    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG if verbose else logging.WARNING)
    sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    sh.addFilter(redact)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def get_logger(name: str = "") -> logging.Logger:
    """Child logger under the studio namespace."""
    return logging.getLogger(f"{_LOGGER_NAME}.{name}" if name else _LOGGER_NAME)
