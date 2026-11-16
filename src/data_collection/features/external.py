"""External knowledge block producing quantitative market signals."""

from __future__ import annotations

from typing import Any, Dict, List
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
        knowledge = payload.get("knowledge", {})

        result: Dict[str, Any] = {
            "market_size_usd": float(market["size_usd"]) if market.get("size_usd") is not None else None,
            "cagr": float(market["cagr"]) if market.get("cagr") is not None else None,
            "competitor_count": int(competition["competitor_count"]) if competition.get("competitor_count") is not None else None,
            "average_sentiment": float(sentiment["average"]) if sentiment.get("average") is not None else None,
            "patent_count": int(compliance["patent_count"]) if compliance.get("patent_count") is not None else None,
            "regulation_mentions": int(compliance["regulation_mentions"]) if compliance.get("regulation_mentions") is not None else None,
            "investor_diversity": float(competition["investor_diversity"]) if competition.get("investor_diversity") is not None else None,
        }

        knowledge_summary: Dict[str, Any] = {
            "company_name": knowledge.get("company_name"),
            "sector": knowledge.get("sector"),
            "product_type": knowledge.get("product_type"),
            "founder_team_complementarity": knowledge.get(
                "founder_team_complementarity"
            ),
            "founder_idea_fit": knowledge.get("founder_idea_fit"),
            "prior_signals": self._safe_list(knowledge.get("prior_signals")),
            "potential_risks": self._safe_list(knowledge.get("potential_risks")),
            "public_sources": self._safe_list(knowledge.get("public_sources")),
            "data_gaps": self._safe_list(knowledge.get("data_gaps")),
            "timestamp_utc": knowledge.get("timestamp_utc"),
        }

        founders_detail = knowledge.get("founders")
        if isinstance(founders_detail, list):
            knowledge_summary["founders"] = founders_detail

        result.update(knowledge_summary)
        return result

    @staticmethod
    def _safe_list(value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        if value is None:
            return []
        return [value]

    @staticmethod
    def summarise_news_sentiment(scores: Dict[str, float]) -> Dict[str, float]:
        values = list(scores.values())
        if not values:
            return {"average": 0.0, "std": 0.0, "count": 0}
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        return {"average": float(mean), "std": float(variance ** 0.5), "count": int(len(values))}


__all__ = ["ExternalKnowledgeBlock"]
