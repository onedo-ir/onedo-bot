import base64
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from playwright.async_api import Browser, Page, async_playwright
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
    await page.click(payload.selector, timeout=15000)
    await page.wait_for_timeout(400)
    return {"url": page.url, "title": await page.title()}


@app.post("/type")
async def type_text(payload: TypeIn):
    page = await ensure_page()
    locator = page.locator(payload.selector).first
    await locator.wait_for(timeout=15000)
    if payload.clear:
        await locator.fill(payload.text)
    else:
        await locator.type(payload.text)
    await page.wait_for_timeout(300)
    return {"url": page.url, "title": await page.title()}


@app.post("/press")
async def press(payload: PressIn):
    page = await ensure_page()
    key = (payload.key or "Enter").strip() or "Enter"
    if payload.selector:
        locator = page.locator(payload.selector).first
        await locator.wait_for(timeout=15000)
        await locator.press(key)
    else:
        await page.keyboard.press(key)
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
    text = await page.locator(payload.selector).first.inner_text(timeout=10000)
    return {"text": text[:20000], "url": page.url}


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
