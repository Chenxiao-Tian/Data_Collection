"""Implementation of the Prediction Block (SSFF Table 2 features)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from .base import FeatureBlock


CATEGORICAL_DEFAULT = "Unknown"


class PredictionFeatureBlock(FeatureBlock):
    """Build structured categorical features for startup fundamentals."""

    name = "prediction_block"

    def build(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        profile = payload.get("profile", {})
        funding = payload.get("funding", {})
        sentiment = payload.get("sentiment", {})
        product = payload.get("product", {})
        hiring = payload.get("hiring", {})

        return {
            "industry_growth": self._infer_industry_growth(profile),
            "market_size": profile.get("market_size", CATEGORICAL_DEFAULT),
            "growth_speed": self._growth_speed(profile, hiring),
            "market_adaptability": product.get("pivot_history", CATEGORICAL_DEFAULT),
            "execution_capability": self._execution(product, hiring),
            "funding_amount": funding.get("stage", CATEGORICAL_DEFAULT),
            "valuation_trend": funding.get("valuation_trend", CATEGORICAL_DEFAULT),
            "investor_quality": funding.get("investor_quality", CATEGORICAL_DEFAULT),
            "pmf_strength": product.get("pmf", CATEGORICAL_DEFAULT),
            "innovation_mentions": product.get("innovation_mentions", CATEGORICAL_DEFAULT),
            "frontier_tech_usage": product.get("frontier_tech_usage", CATEGORICAL_DEFAULT),
            "timing": profile.get("timing", CATEGORICAL_DEFAULT),
            "sentiment": sentiment.get("overall", CATEGORICAL_DEFAULT),
            "reviews": product.get("reviews", CATEGORICAL_DEFAULT),
        }

    # --- heuristics -------------------------------------------------
    def _infer_industry_growth(self, profile: Dict[str, Any]) -> str:
        trend = profile.get("industry_growth")
        if trend:
            return trend
        market_growth = profile.get("market_growth_rate")
        if market_growth is None:
            return CATEGORICAL_DEFAULT
        if market_growth >= 0.15:
            return "Yes"
        if market_growth <= 0:
            return "No"
        return "N/A"

    def _growth_speed(self, profile: Dict[str, Any], hiring: Dict[str, Any]) -> str:
        updates = profile.get("update_frequency_per_month")
        hires = hiring.get("net_new_roles_last_quarter")
        if updates is None and hires is None:
            return CATEGORICAL_DEFAULT
        score = self._to_number(updates) * 0.6 + self._to_number(hires) * 0.4
        if score > 8:
            return "Faster"
        if score < 3:
            return "Slower"
        return "Same"

    def _execution(self, product: Dict[str, Any], hiring: Dict[str, Any]) -> str:
        release_freq = product.get("release_frequency_per_quarter")
        senior_hires = hiring.get("senior_ratio")
        if release_freq is None and senior_hires is None:
            return CATEGORICAL_DEFAULT
        score = 0
        if release_freq is not None:
            score += float(release_freq) / 4
        if senior_hires is not None:
            score += float(senior_hires) * 2
        if score > 1.6:
            return "Excellent"
        if score < 0.8:
            return "Poor"
        return "Average"

    def _to_number(self, value: Optional[float]) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


def annotate_profile(
    *,
    domain: str,
    founded_year: Optional[int],
    market_growth_rate: Optional[float],
    market_size: Optional[str],
    latest_funding_stage: Optional[str],
) -> Dict[str, Any]:
    """Helper used in sample data and tests to generate a profile dict."""

    return {
        "domain": domain,
        "founded_year": founded_year,
        "age": datetime.utcnow().year - founded_year if founded_year else None,
        "market_growth_rate": market_growth_rate,
        "market_size": market_size or CATEGORICAL_DEFAULT,
        "industry_growth": None,
        "update_frequency_per_month": 4,
        "timing": "JustRight",
        "latest_funding_stage": latest_funding_stage,
    }


__all__ = ["PredictionFeatureBlock", "annotate_profile"]
