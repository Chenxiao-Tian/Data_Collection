"""Command-line interface for the startup feature collector."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from data_collection.config import load_from_env
from data_collection.pipeline import run_from_config

app = typer.Typer(add_completion=False)


@app.command(help="Collect features for a single startup.")
def collect(
    name: str = typer.Argument(..., help="Startup name"),
    name: Optional[str] = typer.Option(None, help="Startup name"),
    domain: Optional[str] = typer.Option(None, help="Startup website domain"),
    profile_path: Optional[Path] = typer.Option(
        None, help="Path to a JSON file with pre-annotated signals"
    ),
    industry: str = typer.Option("AI", help="Industry label"),
    stage: str = typer.Option("seed", help="Funding stage"),
    region: str = typer.Option("US", help="Primary operating region"),
    output_dir: Optional[Path] = typer.Option(None, help="Where to write feature tables"),
) -> None:
    load_dotenv()
    config = load_from_env()
    if output_dir:
        config.output_dir = output_dir
        config.output_dir.mkdir(parents=True, exist_ok=True)

    query = {
        "name": name,
        "domain": domain,
        "profile_path": str(profile_path) if profile_path else None,
        "industry": industry,
        "stage": stage,
        "region": region,
    }

    features = run_from_config(config=config, query=query)
    typer.echo(json.dumps(features, indent=2, ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    app()
