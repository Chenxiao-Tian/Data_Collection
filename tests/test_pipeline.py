import asyncio
from pathlib import Path
from typing import Dict
from pathlib import Path

from data_collection.config import RuntimeConfig
from data_collection.pipeline import FeatureCollector
from data_collection.sources.open_data import OpenDataSource


def test_open_data_source_fetch_merges(monkeypatch, tmp_path: Path) -> None:
    config = RuntimeConfig(output_dir=tmp_path / "out", cache_dir=tmp_path / "cache")
    source = OpenDataSource(config=config)

    async def fake_serp(name, domain):
        return {
            "profile": {
                "name": name,
                "domain": "scam.ai",
                "categories": ["Artificial Intelligence"],
            }
        }

    async def fake_jobs(name):
        return {"hiring": {"net_new_roles_last_quarter": 12, "senior_ratio": 0.5}}

    async def fake_sentiment(keyword):
        return {"sentiment": {"overall": "Positive", "average": 0.3, "article_count": 5}}

    async def fake_crunchbase(name):
        return {
            "profile": {"market_size": "Large", "founded_year": 2023},
            "funding": {"stage": "Series A", "valuation_trend": "Increased", "investor_quality": "Top-tier"},
            "founders": [
                {
                    "name": "Ben Ren",
                    "education_level": "PhD",
                    "school_tier": "Tier-1",
                    "leadership_experience": True,
                    "top_company_experience": True,
                    "previous_exits": 1,
                    "role_alignment": 0.9,
                }
            ],
            "market": {"size_usd": 2_500_000_000, "cagr": 0.25},
            "competition": {"competitor_count": 12, "investor_diversity": 0.6},
        }

    async def fake_producthunt(name):
        return {"product": {"pmf": "Strong", "innovation_mentions": "Often", "frontier_tech_usage": "Emphasized", "pivot_history": "Rarely", "reviews": "Positive", "release_frequency_per_quarter": 6}}

    async def fake_compliance(name):
        return {"compliance": {"jurisdiction": "us_ca"}}

    async def fake_proxycurl(founders, domain):
        return list(founders)

    monkeypatch.setattr(source, "_serp_company_overview", fake_serp)
    monkeypatch.setattr(source, "_serp_job_postings", fake_jobs)
    monkeypatch.setattr(source, "_news_sentiment", fake_sentiment)
    monkeypatch.setattr(source, "_crunchbase_profile", fake_crunchbase)
    monkeypatch.setattr(source, "_producthunt_signals", fake_producthunt)
    monkeypatch.setattr(source, "_opencorporates_filings", fake_compliance)
    monkeypatch.setattr(source, "_proxycurl_enrich_founders", fake_proxycurl)

    result = asyncio.run(source.fetch({"name": "Scam AI"}))
    assert result["profile"]["domain"] == "scam.ai"
    assert result["funding"]["stage"] == "Series A"
    assert result["founders"][0]["education_level"] == "PhD"
    assert result["sentiment"]["overall"] == "Positive"
    assert result["competition"]["competitor_count"] == 12


def test_feature_collector_builds_features(monkeypatch, tmp_path: Path) -> None:
    config = RuntimeConfig(output_dir=tmp_path / "out", cache_dir=tmp_path / "cache")
    source = OpenDataSource(config=config)
    collector = FeatureCollector(config=config, sources=[source])

    async def fake_fetch(query: Dict[str, str]):
        return {
def test_pipeline_with_sample_profile(tmp_path: Path):
    config = RuntimeConfig(output_dir=tmp_path / "out", cache_dir=tmp_path / "cache")
    source = OpenDataSource(config=config)
    collector = FeatureCollector(config=config, sources=[source])
    features = collector.prediction.build(
        {
            "profile": {
                "market_size": "Large",
                "market_growth_rate": 0.3,
                "update_frequency_per_month": 10,
                "timing": "JustRight",
            },
            "product": {
                "pivot_history": "Rarely",
                "pmf": "Strong",
                "innovation_mentions": "Often",
                "frontier_tech_usage": "Emphasized",
                "reviews": "Positive",
                "release_frequency_per_quarter": 6,
            },
            "funding": {
                "stage": "Series A",
                "valuation_trend": "Increased",
                "investor_quality": "Top-tier",
            },
            "sentiment": {"overall": "Positive", "average": 0.4},
            "hiring": {"net_new_roles_last_quarter": 8, "senior_ratio": 0.6},
            "market": {"size_usd": 1_000_000_000, "cagr": 0.2},
            "competition": {"competitor_count": 10, "investor_diversity": 0.6},
            "compliance": {"jurisdiction": "us_ca"},
            "founders": [
                {
                    "name": "Founder A",
            "sentiment": {"overall": "Positive"},
            "hiring": {"net_new_roles_last_quarter": 8, "senior_ratio": 0.6},
        }
    )
    assert features["market_size"] == "Large"
    assert features["growth_speed"] == "Faster"

    founder_features = collector.founder.build(
        {
            "founders": [
                {
                    "education_level": "PhD",
                    "school_tier": "Tier-1",
                    "leadership_experience": True,
                    "top_company_experience": True,
                    "previous_exits": 1,
                    "role_alignment": 0.8,
                }
            ],
        }

    monkeypatch.setattr(source, "fetch", fake_fetch)
    features = asyncio.run(collector.collect({"name": "Scam AI"}))

    assert features["features_ssff"]["industry_growth"] == "Yes"
    assert features["features_ssff"]["sentiment"] == "Positive"
    assert features["features_founder"]["founder_level"] == "L5"
    assert features["features_external"]["market_size_usd"] == 1_000_000_000
    assert features["features_external"]["average_sentiment"] == 0.4
            ]
        }
    )
    assert founder_features["founder_level"] == "L5"
    assert founder_features["fifs_score"] == 0.8

    external_features = collector.external.build(
        {
            "market": {"size_usd": 1_000_000_000, "cagr": 0.2},
            "competition": {"competitor_count": 10, "investor_diversity": 0.6},
            "sentiment": {"average": 0.3},
            "compliance": {"patent_count": 4, "regulation_mentions": 2},
        }
    )
    assert external_features["market_size_usd"] == 1_000_000_000
    assert external_features["average_sentiment"] == 0.3
