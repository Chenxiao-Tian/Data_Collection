"""External knowledge block producing quantitative market signals."""

from __future__ import annotations

from typing import Any, Dict

from .base import FeatureBlock


class ExternalKnowledgeBlock(FeatureBlock):
    """Summarise market intelligence from SERP/knowledge graph payloads."""

    name = "external_block"

    def build(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        market = payload.get("market", {})
        competition = payload.get("competition", {})
        sentiment = payload.get("sentiment", {})
        compliance = payload.get("compliance", {})

        return {
            "market_size_usd": float(market.get("size_usd", 0.0)),
            "cagr": float(market.get("cagr", 0.0)),
            "competitor_count": int(competition.get("competitor_count", 0)),
            "average_sentiment": float(sentiment.get("average", 0.0)),
            "patent_count": int(compliance.get("patent_count", 0)),
            "regulation_mentions": int(compliance.get("regulation_mentions", 0)),
            "investor_diversity": float(competition.get("investor_diversity", 0.0)),
        }

    @staticmethod
    def summarise_news_sentiment(scores: Dict[str, float]) -> Dict[str, float]:
        values = list(scores.values())
        if not values:
            return {"average": 0.0, "std": 0.0, "count": 0}
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        return {"average": float(mean), "std": float(variance ** 0.5), "count": int(len(values))}


__all__ = ["ExternalKnowledgeBlock"]
