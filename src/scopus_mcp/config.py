"""Configuration loading via environment variables / .env file."""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

DEFAULT_API_BASE_URL = "https://api.elsevier.com"
DEFAULT_LIMIT = 25


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass
class Config:
    api_key: str
    api_base_url: str = DEFAULT_API_BASE_URL
    content_key: str | None = None
    default_limit: int = DEFAULT_LIMIT
    log_level: str = "WARNING"

    def __post_init__(self) -> None:
        self.api_base_url = self.api_base_url.rstrip("/")

        if not isinstance(self.default_limit, int):
            try:
                self.default_limit = int(self.default_limit)
            except (TypeError, ValueError) as exc:
                raise ConfigurationError("SCOPUS_DEFAULT_LIMIT must be an integer.") from exc

        if self.default_limit < 1:
            raise ConfigurationError("SCOPUS_DEFAULT_LIMIT must be at least 1.")

        if self.default_limit > 100:
            # Scopus API typically rejects requests larger than 100 results per page.
            logger.warning("SCOPUS_DEFAULT_LIMIT > 100 may be rejected by the API")


def configure_logging(config: Config | None = None) -> None:
    """Configure root logging for the application.

    Must be called explicitly from ``main()`` rather than at import time so that
    library consumers and tests are not affected by side effects on import.
    """
    level = (config.log_level if config else os.getenv("LOG_LEVEL", "WARNING")).upper()
    logging.basicConfig(
        stream=sys.stderr,
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def load_config() -> Config:
    """Load configuration from environment variables and an optional .env file."""
    load_dotenv()

    api_key = os.getenv("SCOPUS_API_KEY", "").strip()
    if not api_key:
        raise ConfigurationError(
            "Missing required environment variable: SCOPUS_API_KEY. "
            "Copy .env.example to .env and fill in your Scopus API key "
            "from https://dev.elsevier.com/myapikey.html"
        )

    raw_limit = os.getenv("SCOPUS_DEFAULT_LIMIT", str(DEFAULT_LIMIT))
    try:
        default_limit = int(raw_limit)
    except ValueError as exc:
        raise ConfigurationError("SCOPUS_DEFAULT_LIMIT must be an integer.") from exc

    return Config(
        api_key=api_key,
        api_base_url=os.getenv("SCOPUS_API_BASE_URL", DEFAULT_API_BASE_URL),
        content_key=os.getenv("SCOPUS_CONTENT_KEY") or None,
        default_limit=default_limit,
        log_level=os.getenv("LOG_LEVEL", "WARNING"),
    )
