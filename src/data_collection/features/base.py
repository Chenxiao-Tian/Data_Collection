"""Feature block interfaces."""

from __future__ import annotations

import abc
from typing import Any, Dict


class FeatureBlock(abc.ABC):
    """Base class for feature builders."""

    name: str = "block"

    @abc.abstractmethod
    def build(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a payload into structured features."""


__all__ = ["FeatureBlock"]
