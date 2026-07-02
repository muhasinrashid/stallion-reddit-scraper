"""Logging helper — visible in Apify Console."""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


def log_info(message: str, *args: Any) -> None:
    if args:
        message = message % args
    try:
        from apify import Actor

        Actor.log.info(message)
    except Exception:
        _logger.info(message)


def log_warning(message: str, *args: Any) -> None:
    if args:
        message = message % args
    try:
        from apify import Actor

        Actor.log.warning(message)
    except Exception:
        _logger.warning(message)


def log_error(message: str, *args: Any) -> None:
    if args:
        message = message % args
    try:
        from apify import Actor

        Actor.log.error(message)
    except Exception:
        _logger.error(message)
