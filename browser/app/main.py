import base64
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from playwright.async_api import Browser, Error as PlaywrightError, Locator, Page, async_playwright
from pydantic import BaseModel

WIDTH = 1280
HEIGHT = 800

state: dict[str, Any] = {"playwright": None, "browser": None, "page": None}


class NavigateIn(BaseModel):
    url: str


class ClickIn(BaseModel):
    selector: str


class TypeIn(BaseModel):
    selector: str
    text: str
    clear: bool = True


class ExtractIn(BaseModel):
    selector: str = "body"


class PressIn(BaseModel):
    key: str = "Enter"
    selector: str | None = None


class WaitIn(BaseModel):
    ms: int = 1000


class PointIn(BaseModel):
    x: float
    y: float
    button: str = "left"


class InputTypeIn(BaseModel):
    text: str


class ScrollIn(BaseModel):
    x: float | None = None
    y: float | None = None
    delta_x: float = 0
    delta_y: float = 0


def clamp_point(x: float, y: float) -> tuple[int, int]:
    return (
        max(0, min(WIDTH - 1, int(round(x)))),
        max(0, min(HEIGHT - 1, int(round(y)))),
    )


async def ensure_page() -> Page:
    page: Page | None = state.get("page")
    browser: Browser | None = state.get("browser")
    if page is None or browser is None:
        raise HTTPException(status_code=503, detail="browser not ready")
    return page


def http_playwright_error(exc: Exception) -> HTTPException:
    detail = str(exc).split("\n", 1)[0][:500]
    status = 408 if "Timeout" in type(exc).__name__ or "Timeout" in detail else 422
    return HTTPException(status_code=status, detail=detail)


async def collect_page_actions(page: Page) -> list[dict[str, str]]:
    """Visible actionable tags on the current page only (links, buttons, fields)."""
    try:
        items = await page.evaluate(
            """() => {
  const out = [];
  const seen = new Set();
  const MAX = 120;
  const isVisible = (el) => {
    if (!el || !(el instanceof Element)) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) {
      return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim().slice(0, 120);
  const esc = (s) => String(s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  const textOf = (el) => clean(
    el.innerText || el.value || el.getAttribute('aria-label') ||
    el.getAttribute('title') || el.getAttribute('placeholder') || el.getAttribute('alt') || ''
  );
  const push = (el, kind) => {
    if (out.length >= MAX || !isVisible(el)) return;
    const tag = el.tagName.toLowerCase();
    const text = textOf(el);
    const href = el.getAttribute('href') || '';
    const type = (el.getAttribute('type') || '').toLowerCase();
    const role = el.getAttribute('role') || '';
    const name = el.getAttribute('name') || '';
    const id = el.id || '';
    const key = [tag, kind, href, text, type, name, id].join('|');
    if (seen.has(key)) return;
    seen.add(key);
    let selector = '';
    if (id) {
      selector = '#' + CSS.escape(id);
    } else if (name && (tag === 'input' || tag === 'textarea' || tag === 'select')) {
      selector = tag + '[name="' + esc(name) + '"]';
    } else if (href && tag === 'a') {
      selector = 'a[href="' + esc(href) + '"]';
    } else if (text) {
      selector = tag + ':has-text("' + esc(text.slice(0, 48)) + '")';
    } else if (type) {
      selector = tag + '[type="' + esc(type) + '"]';
    } else {
      selector = tag;
    }
    out.push({ tag, kind, text, href, type, role, name, selector });
  };
  document.querySelectorAll('a[href]').forEach((el) => push(el, 'link'));
  document.querySelectorAll(
    'button, [role="button"], input[type="submit"], input[type="button"], input[type="reset"], input[type="image"]'
  ).forEach((el) => push(el, 'button'));
  document.querySelectorAll('[role="link"]').forEach((el) => push(el, 'link'));
  document.querySelectorAll(
    'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="image"]), textarea, select'
  ).forEach((el) => push(el, 'field'));
  document.querySelectorAll('summary, [onclick]').forEach((el) => {
    if (el.matches('a, button, input, textarea, select, [role="button"], [role="link"]')) return;
    push(el, 'control');
  });
  return out;
}"""
        )
    except PlaywrightError:
        return []
    if not isinstance(items, list):
        return []
    cleaned: list[dict[str, str]] = []
    for raw in items[:120]:
        if not isinstance(raw, dict):
            continue
        cleaned.append(
            {
                "tag": str(raw.get("tag") or "")[:40],
                "kind": str(raw.get("kind") or "")[:40],
                "text": str(raw.get("text") or "")[:120],
                "href": str(raw.get("href") or "")[:500],
                "type": str(raw.get("type") or "")[:40],
                "role": str(raw.get("role") or "")[:40],
                "name": str(raw.get("name") or "")[:80],
                "selector": str(raw.get("selector") or "")[:240],
            }
        )
    return cleaned


async def first_actionable(page: Page, selector: str, timeout: int = 12000) -> Locator:
    """Prefer a visible match; avoid hidden inputs that compound selectors often hit first."""
    sel = (selector or "").strip() or "body"
    base = page.locator(sel)
    visible = base.locator("visible=true").first
    try:
        await visible.wait_for(state="visible", timeout=timeout)
        return visible
    except PlaywrightError:
        pass

    count = min(await base.count(), 20)
    for index in range(count):
        candidate = base.nth(index)
        try:
            if await candidate.is_visible():
                return candidate
        except PlaywrightError:
            continue

    first = base.first
    try:
        await first.wait_for(state="attached", timeout=min(timeout, 4000))
    except PlaywrightError as exc:
        raise http_playwright_error(exc) from exc
    return first


@asynccontextmanager
async def lifespan(_: FastAPI):
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    context = await browser.new_context(
        viewport={"width": WIDTH, "height": HEIGHT},
        locale="fa-IR",
    )
    page = await context.new_page()
    await page.goto("about:blank")
    state["playwright"] = pw
    state["browser"] = browser
    state["page"] = page
    yield
    await browser.close()
    await pw.stop()


app = FastAPI(title="Onedo Browser", lifespan=lifespan)


@app.get("/health")
async def health():
    page = state.get("page")
    return {"status": "ok" if page else "starting", "engine": "chromium"}


@app.get("/current")
async def current():
    page = await ensure_page()
    return {"url": page.url, "title": await page.title()}


@app.post("/navigate")
async def navigate(payload: NavigateIn):
    page = await ensure_page()
    url = payload.url.strip()
    if url and not url.startswith(("http://", "https://", "about:", "data:")):
        url = "https://" + url
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    return {"url": page.url, "title": await page.title()}


@app.post("/click")
async def click(payload: ClickIn):
    page = await ensure_page()
    try:
        locator = await first_actionable(page, payload.selector)
        await locator.click(timeout=10000)
    except HTTPException:
        raise
    except PlaywrightError as exc:
        raise http_playwright_error(exc) from exc
    await page.wait_for_timeout(400)
    return {"url": page.url, "title": await page.title()}


@app.post("/type")
async def type_text(payload: TypeIn):
    page = await ensure_page()
    try:
        locator = await first_actionable(page, payload.selector)
        await locator.click(timeout=5000)
        if payload.clear:
            await locator.fill(payload.text, timeout=10000)
        else:
            await locator.type(payload.text, timeout=10000)
    except HTTPException:
        raise
    except PlaywrightError as exc:
        # Fallback: type into currently focused element
        try:
            if payload.clear:
                await page.keyboard.press("Control+A")
            await page.keyboard.type(payload.text or "", delay=12)
        except PlaywrightError as inner:
            raise http_playwright_error(exc) from inner
    await page.wait_for_timeout(300)
    return {"url": page.url, "title": await page.title()}


@app.post("/press")
async def press(payload: PressIn):
    page = await ensure_page()
    key = (payload.key or "Enter").strip() or "Enter"
    try:
        if payload.selector:
            locator = await first_actionable(page, payload.selector)
            await locator.press(key, timeout=10000)
        else:
            await page.keyboard.press(key)
    except HTTPException:
        raise
    except PlaywrightError as exc:
        raise http_playwright_error(exc) from exc
    await page.wait_for_timeout(400)
    return {"url": page.url, "title": await page.title(), "key": key}


@app.post("/wait")
async def wait(payload: WaitIn):
    page = await ensure_page()
    ms = max(0, min(int(payload.ms or 0), 15000))
    await page.wait_for_timeout(ms)
    return {"url": page.url, "title": await page.title(), "ms": ms}


@app.post("/extract")
async def extract(payload: ExtractIn):
    page = await ensure_page()
    try:
        locator = await first_actionable(page, payload.selector or "body", timeout=8000)
        text = await locator.inner_text(timeout=8000)
    except HTTPException:
        raise
    except PlaywrightError as exc:
        raise http_playwright_error(exc) from exc
    return {"text": text[:20000], "url": page.url}


@app.get("/actions")
async def actions():
    """Interactive tags on the currently open page only (replaced after navigation)."""
    page = await ensure_page()
    items = await collect_page_actions(page)
    return {
        "url": page.url,
        "title": await page.title(),
        "count": len(items),
        "actions": items,
    }


@app.get("/screenshot")
async def screenshot():
    page = await ensure_page()
    raw = await page.screenshot(type="jpeg", quality=55, full_page=False)
    encoded = base64.b64encode(raw).decode("ascii")
    return {
        "image": f"data:image/jpeg;base64,{encoded}",
        "url": page.url,
        "width": WIDTH,
        "height": HEIGHT,
    }


@app.post("/input/click")
async def input_click(payload: PointIn):
    page = await ensure_page()
    x, y = clamp_point(payload.x, payload.y)
    button = payload.button if payload.button in {"left", "right", "middle"} else "left"
    await page.mouse.click(x, y, button=button)
    await page.wait_for_timeout(200)
    return {"url": page.url, "title": await page.title(), "x": x, "y": y, "button": button}


@app.post("/input/dblclick")
async def input_dblclick(payload: PointIn):
    page = await ensure_page()
    x, y = clamp_point(payload.x, payload.y)
    await page.mouse.dblclick(x, y)
    await page.wait_for_timeout(200)
    return {"url": page.url, "title": await page.title(), "x": x, "y": y}


@app.post("/input/type")
async def input_type(payload: InputTypeIn):
    page = await ensure_page()
    text = payload.text or ""
    if text:
        await page.keyboard.type(text, delay=12)
    await page.wait_for_timeout(100)
    return {"url": page.url, "title": await page.title(), "chars": len(text)}


@app.post("/input/scroll")
async def input_scroll(payload: ScrollIn):
    page = await ensure_page()
    if payload.x is not None and payload.y is not None:
        x, y = clamp_point(payload.x, payload.y)
        await page.mouse.move(x, y)
    dx = int(payload.delta_x or 0)
    dy = int(payload.delta_y or 0)
    if dx or dy:
        await page.mouse.wheel(dx, dy)
    await page.wait_for_timeout(80)
    return {
        "url": page.url,
        "title": await page.title(),
        "delta_x": dx,
        "delta_y": dy,
    }


@app.post("/reset")
async def reset():
    page = await ensure_page()
    await page.goto("about:blank")
    return {"url": page.url, "title": await page.title()}
