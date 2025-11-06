"""End-to-end pipeline orchestration for feature collection."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .config import RuntimeConfig
from .features.external import ExternalKnowledgeBlock
from .features.founder import FounderFeatureBlock
from .features.prediction import PredictionFeatureBlock
from .sources.base import DataSource
from .utils import ensure_event_loop


class FeatureCollector:
    """Coordinates data sources and feature builders."""

    def __init__(
        self,
        *,
        config: RuntimeConfig,
        sources: Iterable[DataSource],
    ) -> None:
        self.config = config
        self.sources = list(sources)
        self.prediction = PredictionFeatureBlock()
        self.founder = FounderFeatureBlock()
        self.external = ExternalKnowledgeBlock()

    async def collect(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch data from every source and build features."""

        raw_payloads = await asyncio.gather(
            *(source.fetch(query) for source in self.sources)
        )
        merged = self._merge_payloads(raw_payloads)
        return self._build_features(merged)

    # ------------------------------------------------------------------
    def _merge_payloads(self, payloads: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for payload in payloads:
            for key, value in payload.items():
                if key not in merged:
                    merged[key] = value
                elif isinstance(value, dict):
                    merged[key] = {**merged[key], **value}
                elif isinstance(value, list):
                    merged[key] = [*merged[key], *value]
                else:
                    merged[key] = value
        return merged

    def _build_features(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        prediction = self.prediction.build(payload)
        founder = self.founder.build(payload)
        external = self.external.build(payload)
        return {
            "features_ssff": prediction,
            "features_founder": founder,
            "features_external": external,
        }

    def save(self, features: Dict[str, Any], *, base_path: Path) -> None:
        import pandas as pd

        base_path.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([features["features_ssff"]]).to_parquet(
            base_path / "features_ssff.parquet",
            index=False,
        )
        pd.DataFrame([features["features_founder"]]).to_parquet(
            base_path / "features_founder.parquet",
            index=False,
        )
        pd.DataFrame([features["features_external"]]).to_json(
            base_path / "features_external.json", orient="records", indent=2
        )


async def collect_startup_features(
    *,
    collector: FeatureCollector,
    query: Dict[str, Any],
    output_dir: Path,
) -> Dict[str, Any]:
    features = await collector.collect(query)
    collector.save(features, base_path=output_dir)
    return features


def run_from_config(*, config: RuntimeConfig, query: Dict[str, Any]) -> Dict[str, Any]:
    """Helper used by CLI to execute the pipeline synchronously."""

    from .sources.open_data import OpenDataSource

    collector = FeatureCollector(config=config, sources=[OpenDataSource(config=config)])
    loop = ensure_event_loop()
    return loop.run_until_complete(
        collect_startup_features(
            collector=collector,
            query=query,
            output_dir=config.output_dir,
        )
    )


__all__ = ["FeatureCollector", "collect_startup_features", "run_from_config"]
