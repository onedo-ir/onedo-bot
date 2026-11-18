from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()


class BrowserClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.browser_http_url).rstrip("/")

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request(method, f"{self.base_url}{path}", **kwargs)
            response.raise_for_status()
            return response.json()

    async def health(self) -> dict[str, Any]:
        try:
            return await self._request("GET", "/health")
        except Exception as exc:  # noqa: BLE001
            return {"status": "down", "error": str(exc)}

    async def navigate(self, url: str) -> dict[str, Any]:
        return await self._request("POST", "/navigate", json={"url": url})

    async def click(self, selector: str) -> dict[str, Any]:
        return await self._request("POST", "/click", json={"selector": selector})

    async def type_text(self, selector: str, text: str, clear: bool = True) -> dict[str, Any]:
        return await self._request(
            "POST", "/type", json={"selector": selector, "text": text, "clear": clear}
        )

    async def extract(self, selector: str = "body") -> dict[str, Any]:
        return await self._request("POST", "/extract", json={"selector": selector})

    async def screenshot(self) -> dict[str, Any]:
        return await self._request("GET", "/screenshot")

    async def current(self) -> dict[str, Any]:
        return await self._request("GET", "/current")

    async def reset(self) -> dict[str, Any]:
        return await self._request("POST", "/reset")
