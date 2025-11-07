"""Abstract interfaces for startup data sources."""

from __future__ import annotations

import abc
from typing import Any, Dict, Iterable, List, Optional


class DataSource(abc.ABC):
    """Base class for a data source.

    Each data source exposes a small set of structured signals that can be
    consumed by downstream feature builders. Implementations should avoid
    performing heavy processing so that the same raw payload can be reused.
    """

    name: str = "base"

    def __repr__(self) -> str:  # pragma: no cover - repr is trivial
        return f"{self.__class__.__name__}(name={self.name!r})"

    @abc.abstractmethod
    async def fetch(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch data for a startup.

        Parameters
        ----------
        query:
            Structured query parameters. Implementations are free to decide the
            required keys (for instance, ``{"domain": "example.com"}``).
        """

    def supported_fields(self) -> Optional[Iterable[str]]:
        """Return the list of supported field names, if known."""

        return None


class BatchableDataSource(DataSource):
    """Data source capable of fetching multiple items at once."""

    @abc.abstractmethod
    async def fetch_many(self, queries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fetch multiple payloads in one request."""


__all__ = ["DataSource", "BatchableDataSource"]
