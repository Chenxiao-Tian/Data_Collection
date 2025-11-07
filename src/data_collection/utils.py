"""General utilities for the data collection package."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

import math


def ensure_event_loop() -> asyncio.AbstractEventLoop:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def softmax(scores: Dict[str, float]) -> Dict[str, float]:
    items = list(scores.items())
    if not items:
        return {}
    max_score = max(value for _, value in items)
    exp_values = [math.exp(value - max_score) for _, value in items]
    total = sum(exp_values)
    if total == 0:
        return {key: 0.0 for key, _ in items}
    return {key: exp_val / total for (key, _), exp_val in zip(items, exp_values)}


__all__ = ["ensure_event_loop", "softmax"]
