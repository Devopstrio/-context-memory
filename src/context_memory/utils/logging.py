"""Production-grade structured logging configuration."""
import logging
import re
import sys
from typing import Any

import structlog

from context_memory.config.settings import get_settings

settings = get_settings()


class SensitiveDataFilter:
    """Filter to mask sensitive data in log messages."""

    SENSITIVE_PATTERNS: list[tuple[str, str]] = [
        (r'(?i)(bearer\s+)[^\s]+', r'\1[REDACTED]'),
        (r'(?i)(api[_-]?key[=:]\s*)[^\s,;]+', r'\1[REDACTED]'),
        (r'(?i)(secret[=:]\s*)[^\s,;]+', r'\1[REDACTED]'),
        (r'(?i)(password[=:]\s*)[^\s,;]+', r'\1[REDACTED]'),
        (r'(?i)(token[=:]\s*)[^\s,;]+', r'\1[REDACTED]'),
        (r'"[^"]*@[^"]*"', '"[REDACTED_EMAIL]"'),
        (r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_SSN]'),
        (r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[REDACTED_CC]'),
    ]

    @classmethod
    def mask_sensitive_data(cls, text: str) -> str:
        """Mask sensitive data in text."""
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text


def setup_logging() -> None:
    """Configure structured logging for production use."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]
        ),
    ]

    if settings.environment == "production":
        processors = shared_processors + [
            structlog.processors.JSONRenderer(
                serializer=lambda obj, **kw: __import__("json").dumps(obj, default=str)
            )
        ]
    elif settings.environment == "development":
        processors = shared_processors + [structlog.dev.ConsoleRenderer(colors=True)]
    else:
        processors = shared_processors + [structlog.dev.ConsoleRenderer()]

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        logging.getLogger(logger_name).handlers.clear()
        logging.getLogger(logger_name).addHandler(logging.StreamHandler(sys.stdout))

    if settings.debug:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
    else:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logger = structlog.get_logger(__name__)
    logger.info(
        "Logging configured",
        environment=settings.environment,
        log_level=settings.log_level,
    )
