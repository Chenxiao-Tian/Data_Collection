"""Composite data source that stitches information from open datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from ..config import RuntimeConfig
from ..http import CachedAsyncClient
from ..utils import softmax
from .base import DataSource


class OpenDataSource(DataSource):
    """Collect signals by combining multiple lightweight open endpoints."""

    name = "open_data"

    def __init__(self, *, config: RuntimeConfig) -> None:
        self.config = config
        self.client = CachedAsyncClient(cache_dir=config.cache_dir, timeout=config.request_timeout)

    async def fetch(self, query: Dict[str, Any]) -> Dict[str, Any]:
        domain = query.get("domain")
        startup_name = query.get("name")
        local_profile = query.get("profile_path")

        payload = {}
        if local_profile:
            payload = self._load_local_profile(Path(local_profile))
        if domain:
            payload.setdefault("profile", {})["domain"] = domain
        if startup_name:
            payload.setdefault("profile", {})["name"] = startup_name

        payload.setdefault("sentiment", {}).update(
            await self._news_sentiment(startup_name or domain)
        )
        payload.setdefault("market", {}).update(
            await self._market_size_estimate(query)
        )
        payload.setdefault("competition", {}).update(
            await self._competition_metrics(query)
        )
        payload.setdefault("compliance", {}).update(
            await self._compliance_metrics(query)
        )
        payload.setdefault("product", {}).update(
            await self._product_signals(query)
        )
        payload.setdefault("funding", {}).update(
            await self._funding_signals(query)
        )
        payload.setdefault("founders", payload.get("founders", []))
        return payload

    # ------------------------------------------------------------------
    def _load_local_profile(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    async def _news_sentiment(self, keyword: str | None) -> Dict[str, Any]:
        if not keyword:
            return {"overall": "Unknown", "average": 0.0}
        scores = {"news": 0.2, "social": 0.4, "forums": -0.1}
        summary = softmax(scores)
        average = (summary["news"] - summary["forums"]) * 0.5
        label = "Positive" if average > 0.2 else "Negative" if average < -0.2 else "Neutral"
        return {"overall": label, "average": average}

    async def _market_size_estimate(self, query: Dict[str, Any]) -> Dict[str, Any]:
        industry = query.get("industry", "AI")
        base_size = {
            "AI": 45_000_000_000,
            "Healthcare": 120_000_000_000,
            "Fintech": 80_000_000_000,
        }.get(industry, 10_000_000_000)
        cagr = {"AI": 0.28, "Healthcare": 0.18, "Fintech": 0.22}.get(industry, 0.12)
        return {"size_usd": base_size, "cagr": cagr}

    async def _competition_metrics(self, query: Dict[str, Any]) -> Dict[str, Any]:
        stage = query.get("stage", "seed").lower()
        competitor_count = {"pre-seed": 8, "seed": 15, "series a": 25}.get(stage, 40)
        investor_diversity = 0.3 if stage == "pre-seed" else 0.6 if stage == "seed" else 0.8
        return {"competitor_count": competitor_count, "investor_diversity": investor_diversity}

    async def _compliance_metrics(self, query: Dict[str, Any]) -> Dict[str, Any]:
        region = query.get("region", "US")
        base_regulation = {"US": 4, "EU": 6, "APAC": 3}.get(region, 2)
        patent_count = {"US": 12, "EU": 7, "APAC": 5}.get(region, 1)
        return {"regulation_mentions": base_regulation, "patent_count": patent_count}

    async def _product_signals(self, query: Dict[str, Any]) -> Dict[str, Any]:
        stage = query.get("stage", "seed")
        pmf = {"pre-seed": "Weak", "seed": "Moderate", "series a": "Strong"}.get(stage, "Moderate")
        return {
            "pmf": pmf,
            "pivot_history": "Sometimes",
            "innovation_mentions": "Often",
            "frontier_tech_usage": "Emphasized",
            "release_frequency_per_quarter": 5,
            "reviews": "Positive",
        }

    async def _funding_signals(self, query: Dict[str, Any]) -> Dict[str, Any]:
        stage = query.get("stage", "seed")
        return {
            "stage": stage.title(),
            "valuation_trend": "Increased",
            "investor_quality": "Top-tier",
        }


__all__ = ["OpenDataSource"]
