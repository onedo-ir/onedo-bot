import base64
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from playwright.async_api import BrowserContext, Error as PlaywrightError, Locator, Page, async_playwright
from pydantic import BaseModel

from app.html_tool import HtmlIn, collect_page_html

WIDTH = 1280
HEIGHT = 800
# Shared docker volume browser_data → cookies, localStorage, cache survive restarts.
USER_DATA_DIR = Path("/data/browser/chromium-profile")
# Explicit cookie export for the agent (in addition to Chromium profile).
COOKIES_FILE = Path("/data/browser/cookies.json")

state: dict[str, Any] = {"playwright": None, "context": None, "page": None}


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


class CookieSetIn(BaseModel):
    name: str
    value: str
    domain: str
    path: str = "/"
    expires: float | int | None = None
    httpOnly: bool = False
    secure: bool = False
    sameSite: str | None = "Lax"
    url: str | None = None


class CookieDeleteIn(BaseModel):
    name: str
    domain: str | None = None
    path: str | None = None


def clamp_point(x: float, y: float) -> tuple[int, int]:
    return (
        max(0, min(WIDTH - 1, int(round(x)))),
        max(0, min(HEIGHT - 1, int(round(y)))),
    )


async def ensure_page() -> Page:
    page: Page | None = state.get("page")
    context: BrowserContext | None = state.get("context")
    if page is None or context is None:
        raise HTTPException(status_code=503, detail="browser not ready")
    return page


def ensure_context() -> BrowserContext:
    context: BrowserContext | None = state.get("context")
    if context is None:
        raise HTTPException(status_code=503, detail="browser not ready")
    return context


def _normalize_same_site(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    key = raw.lower()
    mapping = {
        "lax": "Lax",
        "strict": "Strict",
        "none": "None",
    }
    return mapping.get(key, raw if raw in {"Lax", "Strict", "None"} else "Lax")


def cookie_public(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": row.get("name") or "",
        "value": row.get("value") or "",
        "domain": row.get("domain") or "",
        "path": row.get("path") or "/",
        "expires": row.get("expires", -1),
        "httpOnly": bool(row.get("httpOnly")),
        "secure": bool(row.get("secure")),
    }
    same = row.get("sameSite")
    if same:
        out["sameSite"] = same
    return out


async def export_cookies_to_file(context: BrowserContext | None = None) -> dict[str, Any]:
    ctx = context or ensure_context()
    cookies = [cookie_public(c) for c in await ctx.cookies()]
    COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cookies": cookies,
    }
    COOKIES_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(COOKIES_FILE), "count": len(cookies), "cookies": cookies}


def read_cookies_file() -> list[dict[str, Any]]:
    try:
        raw = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("cookies"), list):
        return [c for c in raw["cookies"] if isinstance(c, dict)]
    return []


async def import_cookies_from_file(context: BrowserContext | None = None) -> dict[str, Any]:
    ctx = context or ensure_context()
    rows = read_cookies_file()
    ready: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        value = str(row.get("value") or "")
        domain = str(row.get("domain") or "").strip()
        if not name or not domain:
            continue
        item: dict[str, Any] = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": str(row.get("path") or "/") or "/",
            "httpOnly": bool(row.get("httpOnly")),
            "secure": bool(row.get("secure")),
        }
        expires = row.get("expires")
        if expires is not None:
            try:
                item["expires"] = float(expires)
            except (TypeError, ValueError):
                pass
        same = _normalize_same_site(row.get("sameSite"))
        if same:
            item["sameSite"] = same
        ready.append(item)
    if ready:
        try:
            await ctx.add_cookies(ready)
        except PlaywrightError as exc:
            raise http_playwright_error(exc) from exc
    exported = await export_cookies_to_file(ctx)
    return {"imported": len(ready), **exported}


def http_playwright_error(exc: Exception) -> HTTPException:
    detail = str(exc).split("\n", 1)[0][:500]
    status = 408 if "Timeout" in type(exc).__name__ or "Timeout" in detail else 422
    return HTTPException(status_code=status, detail=detail)


async def collect_page_actions(page: Page) -> list[dict[str, str]]:
    """Visible actionable tags on the current page only (forms, fields, links, buttons)."""
    try:
        # Raw string: a normal """...""" would corrupt JS backslash regexes.
        # Per-kind quotas: links must not starve forms/fields/buttons.
        items = await page.evaluate(
            r"""() => {
  const out = [];
  const seen = new Set();
  const MAX = 160;
  const quota = { form: 15, field: 40, button: 40, link: 50, control: 15 };
  const used = { form: 0, field: 0, button: 0, link: 0, control: 0 };
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
  const esc = (s) => JSON.stringify(String(s || '')).slice(1, -1);
  const labelOf = (el) => {
    const id = el.id || '';
    if (id) {
      try {
        const lab = document.querySelector('label[for="' + CSS.escape(id) + '"]');
        if (lab) return clean(lab.innerText || lab.textContent || '');
      } catch (e) {}
    }
    const wrap = el.closest('label');
    if (wrap) return clean(wrap.innerText || wrap.textContent || '');
    const labelled = el.getAttribute('aria-labelledby');
    if (labelled) {
      const parts = String(labelled).split(/\s+/).map((lid) => {
        const node = document.getElementById(lid);
        return node ? clean(node.innerText || node.textContent || '') : '';
      }).filter(Boolean);
      if (parts.length) return parts.join(' ');
    }
    return '';
  };
  const textOf = (el) => {
    const label = labelOf(el);
    const placeholder = clean(el.getAttribute('placeholder') || '');
    const aria = clean(el.getAttribute('aria-label') || '');
    const visual = clean(
      (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')
        ? (el.value || '')
        : (el.innerText || '')
    );
    return label || placeholder || aria || visual || clean(
      el.getAttribute('title') || el.getAttribute('alt') || el.getAttribute('name') || ''
    );
  };
  // Fields/forms often live in closed drawers (0x0 / aria-hidden). Still list them
  // so the agent knows which inputs exist; keep strict visibility for links/buttons.
  const isFieldCandidate = (el) => {
    if (!el || !(el instanceof Element)) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none') return false;
    return true;
  };
  const formUseful = (el) => {
    if (!el || !(el instanceof Element)) return false;
    if (window.getComputedStyle(el).display === 'none') return false;
    return el.querySelectorAll(
      'input:not([type="hidden"]), textarea, select, [contenteditable="true"], [role="textbox"]'
    ).length > 0 || isVisible(el);
  };
  const push = (el, kind, opts = {}) => {
    const visibleOk = kind === 'form' ? formUseful(el) : (kind === 'field' ? isFieldCandidate(el) : isVisible(el));
    if (out.length >= MAX || used[kind] >= quota[kind] || !visibleOk) return;
    const tag = el.tagName.toLowerCase();
    const text = opts.text != null ? clean(opts.text) : textOf(el);
    const href = opts.href != null ? String(opts.href) : (el.getAttribute('href') || '');
    const type = (el.getAttribute('type') || '').toLowerCase();
    const role = el.getAttribute('role') || '';
    const name = el.getAttribute('name') || '';
    const id = el.id || '';
    const aria = el.getAttribute('aria-label') || '';
    const placeholder = el.getAttribute('placeholder') || '';
    const key = [tag, kind, href, text, type, name, id, aria, placeholder].join('|');
    if (seen.has(key)) return;
    seen.add(key);
    let selector = '';
    if (id) {
      selector = '#' + CSS.escape(id);
    } else if (name && (tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'form')) {
      selector = tag + '[name="' + esc(name) + '"]';
    } else if (href && tag === 'a') {
      selector = 'a[href="' + esc(href) + '"]';
    } else if (placeholder && (tag === 'input' || tag === 'textarea')) {
      selector = tag + '[placeholder="' + esc(placeholder) + '"]';
    } else if (aria) {
      selector = tag + '[aria-label="' + esc(aria) + '"]';
    } else if (text) {
      selector = tag + ':has-text("' + esc(text.slice(0, 48)) + '")';
    } else if (type) {
      selector = tag + '[type="' + esc(type) + '"]';
    } else {
      selector = tag;
    }
    used[kind] += 1;
    out.push({ tag, kind, text, href, type, role, name, selector });
  };
  // Forms + fields first so dense link lists cannot hide them.
  document.querySelectorAll('form').forEach((el) => {
    const action = el.getAttribute('action') || '';
    const fields = el.querySelectorAll(
      'input:not([type="hidden"]), textarea, select, [contenteditable="true"]'
    ).length;
    const label = textOf(el) || clean(el.getAttribute('name') || el.id || 'form');
    push(el, 'form', {
      text: label + (fields ? (' (' + fields + ' fields)') : ''),
      href: action,
    });
  });
  document.querySelectorAll(
    'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="image"]), textarea, select, [contenteditable="true"], [role="textbox"], [role="searchbox"], [role="combobox"]'
  ).forEach((el) => push(el, 'field'));
  document.querySelectorAll(
    'button, [role="button"], [role="tab"], [role="menuitem"], input[type="submit"], input[type="button"], input[type="reset"], input[type="image"]'
  ).forEach((el) => push(el, 'button'));
  document.querySelectorAll('a[href], [role="link"]').forEach((el) => push(el, 'link'));
  document.querySelectorAll('summary, [onclick]').forEach((el) => {
    if (el.matches('a, button, input, textarea, select, form, [role="button"], [role="link"], [role="tab"], [role="menuitem"], [role="textbox"], [contenteditable="true"]')) return;
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
    for raw in items[:160]:
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
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    pw = await async_playwright().start()
    # Persistent profile keeps cookies / localStorage / HTTP cache across container restarts.
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=True,
        viewport={"width": WIDTH, "height": HEIGHT},
        locale="fa-IR",
        accept_downloads=False,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto("about:blank")
    state["playwright"] = pw
    state["context"] = context
    state["page"] = page
    # Merge any agent-managed cookie file into the live context, then re-export.
    try:
        await import_cookies_from_file(context)
    except Exception:  # noqa: BLE001
        try:
            await export_cookies_to_file(context)
        except Exception:  # noqa: BLE001
            pass
    yield
    try:
        await export_cookies_to_file(context)
    except Exception:  # noqa: BLE001
        pass
    await context.close()
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
    try:
        await export_cookies_to_file()
    except Exception:  # noqa: BLE001
        pass
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


@app.post("/html")
async def read_html(payload: HtmlIn):
    """Full/cleaned HTML of the current page (or query windows) for the agent."""
    page = await ensure_page()
    return await collect_page_html(
        page,
        selector=payload.selector or "html",
        query=payload.query,
        max_chars=payload.max_chars,
    )


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


@app.get("/cookies")
async def list_cookies(domain: str | None = None):
    """List browser cookies; optional domain substring filter. Also refreshes cookies.json."""
    context = ensure_context()
    cookies = [cookie_public(c) for c in await context.cookies()]
    needle = (domain or "").strip().lower()
    if needle:
        cookies = [
            c
            for c in cookies
            if needle in (c.get("domain") or "").lower()
            or needle in (c.get("name") or "").lower()
        ]
    try:
        await export_cookies_to_file(context)
    except Exception:  # noqa: BLE001
        pass
    return {
        "path": str(COOKIES_FILE),
        "count": len(cookies),
        "cookies": cookies,
    }


@app.post("/cookies")
async def set_cookie(payload: CookieSetIn):
    """Add or overwrite a cookie, then persist cookies.json."""
    context = ensure_context()
    name = (payload.name or "").strip()
    domain = (payload.domain or "").strip()
    if not name or not domain:
        raise HTTPException(status_code=422, detail="name and domain are required")
    item: dict[str, Any] = {
        "name": name,
        "value": payload.value or "",
        "domain": domain,
        "path": (payload.path or "/") or "/",
        "httpOnly": bool(payload.httpOnly),
        "secure": bool(payload.secure),
    }
    if payload.url:
        item["url"] = payload.url.strip()
    if payload.expires is not None:
        try:
            item["expires"] = float(payload.expires)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="invalid expires") from exc
    same = _normalize_same_site(payload.sameSite)
    if same:
        item["sameSite"] = same
    try:
        await context.add_cookies([item])
    except PlaywrightError as exc:
        raise http_playwright_error(exc) from exc
    exported = await export_cookies_to_file(context)
    return {"ok": True, "cookie": cookie_public(item), **exported}


@app.delete("/cookies")
async def delete_cookie(payload: CookieDeleteIn):
    """Delete cookie(s) by name (+ optional domain/path), then persist cookies.json."""
    context = ensure_context()
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    domain = (payload.domain or "").strip().lower()
    path = (payload.path or "").strip()
    current = await context.cookies()
    remaining: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for row in current:
        row_name = str(row.get("name") or "")
        row_domain = str(row.get("domain") or "").lower()
        row_path = str(row.get("path") or "")
        match = row_name == name
        if match and domain and domain not in row_domain and row_domain not in domain:
            match = False
        if match and path and path != row_path:
            match = False
        if match:
            removed.append(cookie_public(row))
        else:
            remaining.append(row)
    await context.clear_cookies()
    if remaining:
        # Playwright add_cookies rejects some internal-only fields; keep public shape.
        cleaned = [cookie_public(c) for c in remaining]
        # Drop expires=-1 if it confuses some versions — keep as session via omitting?
        ready: list[dict[str, Any]] = []
        for c in cleaned:
            item = {
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path") or "/",
                "httpOnly": bool(c.get("httpOnly")),
                "secure": bool(c.get("secure")),
            }
            exp = c.get("expires")
            if exp is not None and float(exp) > 0:
                item["expires"] = float(exp)
            same = _normalize_same_site(c.get("sameSite"))
            if same:
                item["sameSite"] = same
            ready.append(item)
        try:
            await context.add_cookies(ready)
        except PlaywrightError as exc:
            raise http_playwright_error(exc) from exc
    exported = await export_cookies_to_file(context)
    return {"ok": True, "removed": len(removed), "removed_cookies": removed, **exported}


@app.post("/reset")
async def reset():
    page = await ensure_page()
    await page.goto("about:blank")
    return {"url": page.url, "title": await page.title()}
