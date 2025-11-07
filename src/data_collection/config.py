"""Configuration helpers for the startup feature collector."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass(slots=True)
class APIKeys:
    """Container for API credentials loaded from environment variables."""

    producthunt_token: Optional[str] = None
    serpapi_key: Optional[str] = None
    crunchbase_key: Optional[str] = None
    newsapi_key: Optional[str] = None
    openalex_email: Optional[str] = None
    proxycurl_key: Optional[str] = None
    opencorporates_token: Optional[str] = None

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {
            "producthunt_token": self.producthunt_token,
            "serpapi_key": self.serpapi_key,
            "crunchbase_key": self.crunchbase_key,
            "newsapi_key": self.newsapi_key,
            "openalex_email": self.openalex_email,
            "proxycurl_key": self.proxycurl_key,
            "opencorporates_token": self.opencorporates_token,
        }


@dataclass(slots=True)
class RuntimeConfig:
    """Runtime options for the feature collector."""

    output_dir: Path = field(default_factory=lambda: Path("outputs"))
    cache_dir: Path = field(default_factory=lambda: Path(".cache"))
    api_keys: APIKeys = field(default_factory=APIKeys)
    request_timeout: float = 20.0
    max_concurrency: int = 5

    def model_dump(self) -> Dict[str, object]:  # pragma: no cover - convenience method
        return {
            "output_dir": str(self.output_dir),
            "cache_dir": str(self.cache_dir),
            "api_keys": self.api_keys.as_dict(),
            "request_timeout": self.request_timeout,
            "max_concurrency": self.max_concurrency,
        }


def load_from_env() -> RuntimeConfig:
    """Load configuration from environment variables."""

    import os

    api_keys = APIKeys(
        producthunt_token=os.getenv("PRODUCTHUNT_TOKEN"),
        serpapi_key=os.getenv("SERPAPI_KEY"),
        crunchbase_key=os.getenv("CRUNCHBASE_KEY"),
        newsapi_key=os.getenv("NEWSAPI_KEY"),
        openalex_email=os.getenv("OPENALEX_EMAIL"),
        proxycurl_key=os.getenv("PROXYCURL_API_KEY"),
        opencorporates_token=os.getenv("OPENCORPORATES_APP_TOKEN"),
    )

    output_dir = Path(os.getenv("OUTPUT_DIR", "outputs"))
    cache_dir = Path(os.getenv("CACHE_DIR", ".cache"))
    request_timeout = float(os.getenv("REQUEST_TIMEOUT", "20"))
    max_concurrency = int(os.getenv("MAX_CONCURRENCY", "5"))

    config = RuntimeConfig(
        output_dir=output_dir,
        cache_dir=cache_dir,
        api_keys=api_keys,
        request_timeout=request_timeout,
        max_concurrency=max_concurrency,
    )
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    return config


__all__ = ["APIKeys", "RuntimeConfig", "load_from_env"]
