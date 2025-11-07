"""HTTP utilities with caching and concurrency support."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import request


class CachedAsyncClient:
    """Lightweight HTTP client implemented with the standard library."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        timeout: float = 20.0,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self._timeout = timeout
        self._headers = headers or {}
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def get_json(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        cache_key = self._cache_key("GET", url, params, headers)
    async def get_json(self, url: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        cache_key = self._cache_key("GET", url, params)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"
        data = await asyncio.to_thread(self._sync_request, url, None, headers=headers)
        data = await asyncio.to_thread(self._sync_request, url, None)
        self._write_cache(cache_key, data)
        return data

    async def post_json(
        self,
        url: str,
        payload: Dict[str, Any],
        *,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        cache_key = self._cache_key("POST", url, payload, headers)
        cache_key = self._cache_key("POST", url, payload)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        data = await asyncio.to_thread(
            self._sync_request,
            url,
            json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        self._write_cache(cache_key, data)
        return data

    async def close(self) -> None:  # pragma: no cover - kept for API parity
        return None

    # Internal helpers -------------------------------------------------
    def _sync_request(
        self, url: str, payload: Optional[bytes], headers: Optional[Dict[str, str]] = None
    ) -> Any:
        req = request.Request(url, data=payload, method="POST" if payload else "GET")
        all_headers = {**self._headers, **(headers or {})}
        for key, value in all_headers.items():
            req.add_header(key, value)
        with request.urlopen(req, timeout=self._timeout) as resp:
            content = resp.read().decode("utf-8")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content

    def _cache_key(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]],
        headers: Optional[Dict[str, str]],
    ) -> str:
        serialized = json.dumps(
            {"url": url, "params": params, "method": method, "headers": headers},
            sort_keys=True,
        )
    def _cache_key(self, method: str, url: str, params: Optional[Dict[str, Any]]) -> str:
        serialized = json.dumps({"url": url, "params": params, "method": method}, sort_keys=True)
        return str(abs(hash(serialized)))

    def _read_cache(self, key: str) -> Optional[Any]:
        path = self._cache_dir / f"{key}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _write_cache(self, key: str, data: Any) -> None:
        path = self._cache_dir / f"{key}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)


async def gather_with_concurrency(limit: int, *tasks: Any) -> Any:
    """Wrapper around :func:`asyncio.gather` enforcing concurrency limits."""

    semaphore = asyncio.Semaphore(limit)

    async def sem_task(task):
        async with semaphore:
            return await task

    return await asyncio.gather(*(sem_task(t) for t in tasks))


__all__ = ["CachedAsyncClient", "gather_with_concurrency"]
