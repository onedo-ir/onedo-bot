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
    if not url.startswith("http"):
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
    return {"image": f"data:image/jpeg;base64,{encoded}", "url": page.url}


@app.post("/reset")
async def reset():
    page = await ensure_page()
    await page.goto("about:blank")
    return {"url": page.url, "title": await page.title()}
