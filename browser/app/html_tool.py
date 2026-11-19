"""HTML inspection helpers for the browser agent (read_html)."""
from typing import Any

from fastapi import HTTPException
from playwright.async_api import Error as PlaywrightError, Page
from pydantic import BaseModel


class HtmlIn(BaseModel):
    """Read page HTML so the agent can locate selectors itself."""

    selector: str = "html"
    query: str | None = None
    max_chars: int = 60000


def _playwright_http_error(exc: Exception) -> HTTPException:
    detail = str(exc).split("\n", 1)[0][:500]
    status = 408 if "Timeout" in type(exc).__name__ or "Timeout" in detail else 422
    return HTTPException(status_code=status, detail=detail)


async def collect_page_html(
    page: Page,
    *,
    selector: str = "html",
    query: str | None = None,
    max_chars: int = 60000,
) -> dict[str, Any]:
    """Return cleaned HTML (or query-matched windows) for agent inspection."""
    sel = (selector or "html").strip() or "html"
    limit = max(2000, min(int(max_chars or 60000), 120000))
    q = (query or "").strip()
    try:
        locator = page.locator(sel).first
        await locator.wait_for(state="attached", timeout=8000)
        compact = await locator.evaluate(
            r"""(el) => {
  const clone = el.cloneNode(true);
  clone.querySelectorAll('script, style, noscript, svg, link[rel="stylesheet"]').forEach((n) => n.remove());
  clone.querySelectorAll('[src^="data:"]').forEach((n) => n.removeAttribute('src'));
  return (clone.outerHTML || '').replace(/\s+/g, ' ').trim();
}"""
        )
    except PlaywrightError as exc:
        raise _playwright_http_error(exc) from exc

    compact = str(compact or "")
    mode = "full"
    matches = 0
    if q:
        mode = "query"
        hay = compact
        lower_hay = hay.lower()
        lower_q = q.lower()
        windows: list[str] = []
        from_idx = 0
        radius = 450
        while len(windows) < 12:
            idx = lower_hay.find(lower_q, from_idx)
            if idx < 0:
                break
            start = max(0, idx - radius)
            end = min(len(hay), idx + len(q) + radius)
            windows.append(
                "--- match "
                + str(len(windows) + 1)
                + " @"
                + str(idx)
                + " ---\n"
                + hay[start:end]
            )
            from_idx = idx + max(len(q), 1)
            matches += 1
        html = "\n\n".join(windows)
    else:
        html = compact

    truncated = False
    if len(html) > limit:
        html = html[:limit]
        truncated = True

    return {
        "html": html,
        "url": page.url,
        "title": await page.title(),
        "selector": sel,
        "query": q,
        "length": len(html),
        "truncated": truncated,
        "matches": matches,
        "mode": mode,
    }
