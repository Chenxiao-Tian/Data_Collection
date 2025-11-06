"""Founder Segmentation Block implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from .base import FeatureBlock


FOUNDER_LEVELS = ["L1", "L2", "L3", "L4", "L5"]


@dataclass
class FounderProfile:
    name: str
    education_level: str
    school_tier: str
    leadership_experience: bool
    top_company_experience: bool
    previous_exits: int
    role_alignment: float


class FounderFeatureBlock(FeatureBlock):
    """Compute founder-level categorical and numerical indicators."""

    name = "founder_block"

    def build(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        founders: Iterable[Dict[str, Any]] = payload.get("founders", [])
        founder_profiles = [self._parse_founder(f) for f in founders]
        if not founder_profiles:
            return {
                "founder_level": "L1",
                "fifs_score": 0.0,
                "founder_count": 0,
            }
        level = self._aggregate_level(founder_profiles)
        alignments = [f.role_alignment for f in founder_profiles]
        fifs_score = float(sum(alignments) / len(alignments))
        normalized = max(min(fifs_score, 1.0), -1.0)
        return {
            "founder_level": level,
            "fifs_score": normalized,
            "founder_count": len(founder_profiles),
        }

    def _parse_founder(self, founder: Dict[str, Any]) -> FounderProfile:
        return FounderProfile(
            name=founder.get("name", "Unknown"),
            education_level=founder.get("education_level", "Unknown"),
            school_tier=founder.get("school_tier", "Unknown"),
            leadership_experience=bool(founder.get("leadership_experience", False)),
            top_company_experience=bool(founder.get("top_company_experience", False)),
            previous_exits=int(founder.get("previous_exits", 0)),
            role_alignment=float(founder.get("role_alignment", 0.0)),
        )

    def _aggregate_level(self, founders: List[FounderProfile]) -> str:
        score = 0.0
        for founder in founders:
            score += self._education_score(founder.education_level, founder.school_tier)
            score += 1.0 if founder.leadership_experience else 0.0
            score += 1.5 if founder.top_company_experience else 0.0
            score += min(founder.previous_exits, 2) * 1.5
        avg_score = score / max(len(founders), 1)
        if avg_score >= 5.0:
            return "L5"
        if avg_score >= 4.0:
            return "L4"
        if avg_score >= 3.0:
            return "L3"
        if avg_score >= 1.5:
            return "L2"
        return "L1"

    def _education_score(self, level: str, tier: str) -> float:
        level = level.lower()
        tier = tier.lower()
        base = {
            "phd": 2.5,
            "masters": 2.0,
            "bachelors": 1.5,
            "associate": 1.0,
        }.get(level, 0.5)
        tier_bonus = {"tier-1": 1.5, "tier-2": 1.0, "tier-3": 0.5}.get(tier, 0.0)
        return base + tier_bonus


__all__ = ["FounderFeatureBlock", "FounderProfile", "FOUNDER_LEVELS"]
