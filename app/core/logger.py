"""Central logger setup used by API, services, and skills."""

from __future__ import annotations

import logging

from app.core.config import settings


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger instance."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    return logging.getLogger(name)

