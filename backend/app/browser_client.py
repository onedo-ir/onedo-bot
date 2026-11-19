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

    async def press(self, key: str = "Enter", selector: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"key": key}
        if selector:
            payload["selector"] = selector
        return await self._request("POST", "/press", json=payload)

    async def wait(self, ms: int = 1000) -> dict[str, Any]:
        return await self._request("POST", "/wait", json={"ms": ms})

    async def extract(self, selector: str = "body") -> dict[str, Any]:
        return await self._request("POST", "/extract", json={"selector": selector})

    async def screenshot(self) -> dict[str, Any]:
        return await self._request("GET", "/screenshot")

    async def current(self) -> dict[str, Any]:
        return await self._request("GET", "/current")

    async def reset(self) -> dict[str, Any]:
        return await self._request("POST", "/reset")

    async def input_click(self, x: float, y: float, button: str = "left") -> dict[str, Any]:
        return await self._request(
            "POST", "/input/click", json={"x": x, "y": y, "button": button}
        )

    async def input_dblclick(self, x: float, y: float) -> dict[str, Any]:
        return await self._request("POST", "/input/dblclick", json={"x": x, "y": y})

    async def input_type(self, text: str) -> dict[str, Any]:
        return await self._request("POST", "/input/type", json={"text": text})

    async def input_scroll(
        self,
        delta_x: float = 0,
        delta_y: float = 0,
        x: float | None = None,
        y: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"delta_x": delta_x, "delta_y": delta_y}
        if x is not None:
            payload["x"] = x
        if y is not None:
            payload["y"] = y
        return await self._request("POST", "/input/scroll", json=payload)
