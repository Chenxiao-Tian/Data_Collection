from pathlib import Path

from data_collection.config import RuntimeConfig
from data_collection.pipeline import FeatureCollector
from data_collection.sources.open_data import OpenDataSource


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
