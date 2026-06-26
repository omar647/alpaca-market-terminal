"""Configuration: load Alpaca API keys and settings from environment variables.

Keys are read from a local ``.env`` file (via python-dotenv) or the real
environment. Nothing secret is ever hard-coded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load variables from a .env file in the project root, if present.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime settings sourced from environment variables."""

    api_key: str
    secret_key: str
    data_feed: str = "iex"  # "iex" (free) or "sip" (paid)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self.secret_key)


def load_settings() -> Settings:
    """Build a :class:`Settings` object from the environment.

    Raises
    ------
    RuntimeError
        If the required API keys are missing — with a helpful hint.
    """
    api_key = os.getenv("ALPACA_API_KEY", "").strip()
    secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
    data_feed = os.getenv("ALPACA_DATA_FEED", "iex").strip() or "iex"

    settings = Settings(api_key=api_key, secret_key=secret_key, data_feed=data_feed)
    if not settings.is_configured:
        raise RuntimeError(
            "Alpaca API keys not found. Copy .env.example to .env and set "
            "ALPACA_API_KEY and ALPACA_SECRET_KEY (use your *paper* keys)."
        )
    return settings
