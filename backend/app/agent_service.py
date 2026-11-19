import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.browser_agent_lock import (
    BrowserControlCancelled,
    acquire_browser_control,
    is_browser_agent_busy,
)
from app.browser_client import BrowserClient
from app.chat_memory import (
    format_chat_memory_for_prompt,
    load_chat_memory,
    record_click,
    record_field,
    record_links_from_actions,
    record_navigate,
)
from app.config import get_settings
from app.models import AgentTask, Message, MessageRole, TaskStatus
from app.schedule_service import (
    create_scheduled_task,
    format_schedules_for_prompt,
    list_scheduled_tasks,
)

MAX_STEPS = 15
# Persistent file vault (no panel UI / no DB table). Shared browser_data volume.
CREDENTIALS_FILE = Path("/data/browser/credentials.json")
COOKIES_FILE = Path("/data/browser/cookies.json")

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+98|0)?9\d{9}(?!\d)|(?<!\d)0\d{10,11}(?!\d)")
_URL_RE = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.I)

# Only for homepage grounding when the user named the site (never deep paths).
_SITE_ALIASES: dict[str, tuple[str, ...]] = {
    "digikala": ("digikala", "دیجی کالا", "دیجیکالا", "دیجی‌کالا"),
    "snapp": ("snapp", "اسنپ"),
    "tapsi": ("tapsi", "تپسی"),
    "divar": ("divar", "دیوار"),
    "torob": ("torob", "ترب"),
    "google": ("google", "گوگل"),
    "github": ("github", "گیت‌هاب", "گیتهاب"),
    "linkedin": ("linkedin", "لینکدین", "لینک‌دین"),
}


def resolve_ai_config() -> tuple[str, str, str]:
    settings = get_settings()
    api_key = (settings.openai_compatible_api_key or "").strip()
    base_url = (settings.openai_compatible_base_url or "").rstrip("/")
    model = (settings.openai_compatible_model or "auto").strip() or "auto"
    return api_key, base_url, model


def _read_credentials_file() -> list[dict[str, Any]]:
    try:
        if not CREDENTIALS_FILE.exists():
            return []
        raw = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    items: list[dict[str, Any]] = []
    for row in raw:
        if isinstance(row, dict):
            items.append(row)
    return items


def _write_credentials_file(items: list[dict[str, Any]]) -> None:
    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_vault() -> list[dict[str, Any]]:
    return _read_credentials_file()


def format_cookies_file_for_prompt(*, max_rows: int = 40) -> str:
    """Compact cookie index for the LLM (names/domains; values truncated)."""
    try:
        raw = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return f"(empty or missing — {COOKIES_FILE})"
    rows: list[Any]
    if isinstance(raw, dict):
        rows = raw.get("cookies") if isinstance(raw.get("cookies"), list) else []
        updated = raw.get("updated_at") or "-"
    elif isinstance(raw, list):
        rows = raw
        updated = "-"
    else:
        return f"(empty or missing — {COOKIES_FILE})"
    lines = [f"file={COOKIES_FILE} updated_at={updated} count={len(rows)}"]
    for row in rows[:max_rows]:
        if not isinstance(row, dict):
            continue
        value = str(row.get("value") or "")
        if len(value) > 24:
            value = value[:12] + "…" + value[-6:]
        lines.append(
            f"- name={row.get('name') or '-'} | domain={row.get('domain') or '-'} | "
            f"path={row.get('path') or '/'} | value={value or '-'}"
        )
    if len(rows) > max_rows:
        lines.append(f"… +{len(rows) - max_rows} more (use list_cookies)")
    return "\n".join(lines)


def format_vault_for_prompt(items: list[dict[str, Any]]) -> str:
    if not items:
        return "(empty — file /data/browser/credentials.json)"
    lines = []
    for item in items:
        lines.append(
            f"- id={item.get('id')} | label={item.get('label') or '-'} | "
            f"site={item.get('site_url') or '-'} | username={item.get('username') or '-'} | "
            f"note={item.get('secret_note') or '-'}"
        )
    return "\n".join(lines)


def format_page_actions_for_prompt(actions: list[dict[str, Any]], *, limit: int = 100) -> str:
    """Only the current page's interactive tags; caller replaces this on every URL change."""
    if not actions:
        return "(none)"
    lines: list[str] = []
    for item in actions[:limit]:
        kind = (item.get("kind") or "control").strip()
        tag = (item.get("tag") or "?").strip()
        text = (item.get("text") or "").strip()
        href = (item.get("href") or "").strip()
        typ = (item.get("type") or "").strip()
        name = (item.get("name") or "").strip()
        selector = (item.get("selector") or "").strip()
        parts = [f"[{kind}]", tag]
        if text:
            parts.append(f'text="{text[:80]}"')
        if href:
            # For forms this holds the action URL when present.
            parts.append(f'href="{href[:220]}"')
        if typ:
            parts.append(f"type={typ}")
        if name:
            parts.append(f"name={name}")
        if selector:
            parts.append(f"selector={selector}")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)


def save_vault_item(
    *,
    label: str,
    site_url: str = "",
    username: str = "",
    secret_note: str = "",
) -> dict[str, Any]:
    items = _read_credentials_file()
    next_id = 1
    for row in items:
        try:
            next_id = max(next_id, int(row.get("id") or 0) + 1)
        except (TypeError, ValueError):
            continue
    item = {
        "id": next_id,
        "label": (label or "بدون برچسب").strip()[:255],
        "site_url": (site_url or "").strip()[:1024],
        "username": (username or "").strip()[:255],
        "secret_note": (secret_note or "").strip(),
    }
    items.append(item)
    _write_credentials_file(items)
    return item


def append_step(task: AgentTask, step: dict[str, Any]) -> None:
    try:
        steps = json.loads(task.steps_log or "[]")
    except json.JSONDecodeError:
        steps = []
    step["step"] = len(steps) + 1
    steps.append(step)
    task.steps_log = json.dumps(steps, ensure_ascii=False)


def parse_llm_json(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    raise ValueError("پاسخ مدل JSON معتبر نبود")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _evidence_corpus(
    instruction: str,
    page_url: str,
    page_text: str,
    vault_text: str,
    history: list[dict[str, Any]],
    last_extract: str = "",
    page_actions_text: str = "",
    chat_memory_text: str = "",
) -> str:
    parts = [
        instruction,
        page_url,
        page_text,
        vault_text,
        last_extract,
        page_actions_text,
        chat_memory_text,
    ]
    for item in history[-12:]:
        parts.append(str(item.get("detail") or ""))
        parts.append(str(item.get("reason") or ""))
        parts.append(str(item.get("action") or ""))
    return _norm("\n".join(parts))


def _action_text_for_selector(
    page_actions: list[dict[str, Any]] | None, selector: str
) -> str:
    sel = (selector or "").strip()
    if not sel or not page_actions:
        return ""
    for item in page_actions:
        if (item.get("selector") or "").strip() == sel:
            return (item.get("text") or "").strip()[:120]
    return ""


def _host_stem(host: str) -> str:
    host = (host or "").lower().removeprefix("www.")
    if not host:
        return ""
    return host.split(".")[0]


def _normalize_navigate_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://", "about:", "data:")):
        return raw
    return "https://" + raw


def is_url_grounded(url: str, corpus: str) -> bool:
    """Allow navigate only when URL/domain is evidenced; block invented deep paths."""
    full = _normalize_navigate_url(url)
    if not full or full.startswith("about:"):
        return True
    parsed = urlparse(full)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = parsed.path or "/"
    full_l = full.lower()
    host_l = host.lower()
    path_l = path.lower()

    if full_l in corpus or full_l.replace("https://", "").replace("http://", "") in corpus:
        return True
    if host_l and host_l in corpus:
        # Homepage / shallow path OK when domain is known from evidence
        if path_l in {"", "/", "/fa", "/en", "/home", "/index.html"}:
            return True
        if path_l in corpus or path_l.rstrip("/") in corpus:
            return True
        # Deep path not seen anywhere → treat as guess
        return False

    stem = _host_stem(host)
    shallow = path_l in {"", "/", "/fa", "/en", "/home", "/index.html"}
    # Brand mentioned as latin stem in evidence (e.g. digikala)
    if stem and len(stem) >= 4 and stem in corpus.replace(" ", ""):
        return shallow
    # Persian/English aliases only unlock the homepage, never invented deep links
    aliases = _SITE_ALIASES.get(stem, ())
    if shallow and aliases and any(_norm(alias) in corpus for alias in aliases):
        return True
    return False


def looks_like_invented_secret(text: str, corpus: str) -> bool:
    value = (text or "").strip()
    if not value or len(value) < 5:
        return False
    if value.lower() in corpus:
        return False
    if _EMAIL_RE.fullmatch(value):
        return True
    if _PHONE_RE.fullmatch(re.sub(r"[\s-]", "", value)):
        return True
    # Long digit codes / OTPs not present in evidence
    if re.fullmatch(r"\d{4,8}", value) and value not in corpus:
        return True
    return False


def apply_decision_guardrails(
    decision: dict[str, Any],
    *,
    instruction: str,
    page_url: str,
    page_text: str,
    vault_text: str,
    history: list[dict[str, Any]],
    last_extract: str = "",
    page_actions_text: str = "",
    chat_memory_text: str = "",
) -> dict[str, Any]:
    """Hard guardrails: do not invent URLs/values; prefer page evidence; ask when unsure."""
    out = dict(decision or {})
    action = (out.get("action") or "").lower().strip()
    corpus = _evidence_corpus(
        instruction,
        page_url,
        page_text,
        vault_text,
        history,
        last_extract,
        page_actions_text,
        chat_memory_text,
    )
    blank = (page_url or "").startswith("about:blank") or not (page_url or "").strip()

    if action == "navigate":
        url = _normalize_navigate_url(str(out.get("url") or ""))
        out["url"] = url
        if not is_url_grounded(url, corpus):
            return {
                "action": "ask",
                "question": (
                    "آدرس مطمئنی برای رفتن پیدا نکردم و نمی‌خواهم حدس بزنم. "
                    "لطفاً URL دقیق را بفرستید، یا بگویید از کدام لینک/صفحهٔ فعلی استفاده کنم."
                ),
                "reason": "guardrail_unguessed_url",
                "blocked_url": url,
            }

    if action == "type":
        text = str(out.get("text") or "")
        if looks_like_invented_secret(text, corpus):
            return {
                "action": "ask",
                "question": (
                    "مقدار حساس/شناسه‌ای که برای تایپ لازم است در پیام شما، خزانه، "
                    "یا متن صفحه نیست و نباید حدس زده شود. لطفاً همان مقدار را بفرستید."
                ),
                "reason": "guardrail_unguessed_value",
            }

    if action == "done":
        summary = str(out.get("summary") or "")
        # If summarizing page facts but never extracted and page has content, force extract once
        extracted_before = any(
            (h.get("action") or "") in {"extract", "read_html", "done"} for h in history
        )
        if (
            not blank
            and page_text.strip()
            and not extracted_before
            and not (last_extract or "").strip()
            and len(summary) > 40
        ):
            return {
                "action": "extract",
                "selector": "body",
                "reason": "guardrail_extract_before_done",
            }

        for found in _URL_RE.findall(summary):
            if not is_url_grounded(found, corpus):
                return {
                    "action": "ask",
                    "question": (
                        "در خلاصه آدرسی آمده که از صفحه/دستور شما استخراج نشده. "
                        "کدام منبع را مبنا قرار بدهم، یا خودتان تأیید کنید؟"
                    ),
                    "reason": "guardrail_summary_url",
                }

    return out


async def call_llm_next_action(
    instruction: str,
    page_url: str,
    page_title: str,
    page_text: str,
    history: list[dict[str, Any]],
    vault_text: str,
    page_actions_text: str = "(none)",
    last_extract: str = "",
    schedules_text: str = "(none)",
    chat_memory_text: str = "(empty)",
    cookies_text: str = "(empty)",
) -> dict[str, Any]:
    api_key, base_url, model = resolve_ai_config()

    if not api_key:
        return {
            "action": "ask",
            "question": (
                "کلید API ایجنت تنظیم نشده. متغیر محیطی "
                "OPENAI_COMPATIBLE_API_KEY را در .env تنظیم کنید."
            ),
            "reason": "missing_api_key",
        }

    system = (
        "You are Onedo bot, a careful browser agent for Persian users.\n"
        "Decide ONLY the single next action. Return STRICT JSON object with keys:\n"
        "  action: one of navigate|click|type|press|wait|extract|read_html|"
        "save_credential|list_cookies|set_cookie|delete_cookie|"
        "schedule_periodic_task|ask|done\n"
        "  url (navigate), selector (click/type/extract/read_html), text (type),\n"
        "  query (optional search string for read_html),\n"
        "  key (press, e.g. Enter), ms (wait), question (ask),\n"
        "  label/site_url/username/secret_note (save_credential),\n"
        "  domain (optional filter for list_cookies),\n"
        "  name/value/domain/path/expires/httpOnly/secure/sameSite "
        "(set_cookie; name+value+domain required),\n"
        "  name/domain/path (delete_cookie; name required),\n"
        "  title/interval_minutes/steps/run_immediately (schedule_periodic_task),\n"
        "  summary (Persian, for done), reason (short).\n"
        "\n"
        "HARD GUARDRAILS (never violate):\n"
        "1) NEVER invent or guess: URLs, deep paths, phone numbers, emails, OTPs, "
        "prices, order ids, selectors, credentials, or form values.\n"
        "2) Evidence only: use facts from (a) the user instruction, (b) credential "
        "file, (c) current page URL/title/text, (d) CURRENT-page interactive "
        "elements list (forms/fields/buttons/links), (e) prior extract/read_html results.\n"
        "3) If a needed URL/value is missing from evidence → action=ask. Do not "
        "fabricate digikala/deep links, tracking URLs, or login fields.\n"
        "4) On a loaded page: prefer click/type using selectors/hrefs from the "
        "CURRENT interactive elements list (forms, fields, links, buttons). That "
        "list is replaced whenever the page/URL changes — never reuse old-page controls.\n"
        "5) navigate is allowed only for a URL the user gave, a link/domain clearly "
        "present in page/actions/credentials file, or the site homepage when the user "
        "named that site. Never invent /product/... or query URLs.\n"
        "6) Do NOT open Google/Bing unless the user explicitly asked to search there.\n"
        "7) After typing in a real visible field, press Enter or click the submit "
        "control that is evidenced on the page.\n"
        "8) Selectors: ONE specific visible control from the current actions list "
        "when possible. No broad comma-separated lists.\n"
        "9) If a previous action failed: change approach from page evidence, or ask.\n"
        "10) done summary must only state evidenced facts (from page/extract/user). "
        "If unsure, ask or extract again.\n"
        "11) Credentials are stored only in a private file (not the panel). Read them "
        "from context and use save_credential when the user asks to remember login info.\n"
        "11b) Per-chat memory file stores important URLs, clicked button selectors, typed "
        "fields, and key links for THIS conversation. Prefer reusing those evidenced "
        "selectors/URLs when you return to the same page. Do not invent new ones.\n"
        "11c) Browser cookies are exported to /data/browser/cookies.json. Use "
        "list_cookies / set_cookie / delete_cookie when the user asks to inspect, add, "
        "or remove cookies (name+domain required for set; never invent cookie values).\n"
        "12) Pure Q&A with no browsing needed → done with a Persian answer.\n"
        "13) When interactive list/text is not enough to find a control or structure, "
        "use read_html (optionally with query=keyword) to inspect cleaned HTML and "
        "derive a real selector from it — then click/type. Prefer query search over "
        "dumping the whole page when you know a keyword.\n"
        "14) When the user asks to run something periodically/recurring, use "
        "schedule_periodic_task (do NOT just say you will remember). Required fields:\n"
        "  - title: short Persian title\n"
        "  - interval_minutes: integer minutes between runs (min 5). "
        "Convert phrases like every 2 hours→120, daily→1440.\n"
        "  - steps: a DETAILED numbered playbook the FUTURE agent will follow blindly. "
        "MUST include concrete browser actions with evidenced URLs/selectors/button text "
        "from this session (user instruction + current page actions + history). "
        "Preferred format example:\n"
        "    1. navigate → url=https://example.com/login\n"
        "    2. click → selector=button.login | text=\"ورود\"\n"
        "    3. type → selector=input[name=user] | text=<from credentials/user>\n"
        "    4. press → key=Enter\n"
        "    5. extract → selector=body | check that …\n"
        "    6. done when …\n"
        "Never invent deep URLs/selectors. If you have not yet discovered the real "
        "controls, browse/extract first OR ask — do not schedule vague steps.\n"
        "  - run_immediately: optional bool (default false)\n"
        "If interval or steps are unclear/vague → ask first. After scheduling → done with "
        "confirmation (id + interval).\n"
        "Respond with JSON only."
    )
    history_lines = []
    for item in history[-12:]:
        history_lines.append(
            f"- {item.get('action')}: {item.get('detail') or item.get('reason') or ''}"
        )
    last_block = (last_extract or "").strip()
    user_prompt = (
        f"User instruction:\n{instruction}\n\n"
        f"Current page URL: {page_url or 'about:blank'}\n"
        f"Current page title: {page_title or ''}\n\n"
        f"Credentials file (agent-only; /data/browser/credentials.json):\n{vault_text}\n\n"
        f"Browser cookies file (agent-only; /data/browser/cookies.json):\n{cookies_text}\n\n"
        "This chat's memory (agent-only; /data/browser/chat_memory/{id}.json) — "
        "clicked buttons, important links/URLs, typed fields:\n"
        f"{chat_memory_text}\n\n"
        "Existing periodic schedules (DB + /data/browser/scheduled_tasks/*.md):\n"
        f"{schedules_text}\n\n"
        "Interactive elements on CURRENT page only "
        "(forms/fields/buttons/links; previous page cleared):\n"
        f"{page_actions_text[:4000]}\n\n"
        f"Recent actions:\n"
        + ("\n".join(history_lines) if history_lines else "(none)")
        + "\n\n"
        "Reminder: do not guess URLs or values; use current-page actions + text "
        "(+ read_html when you need raw markup).\n\n"
        f"Visible page text (truncated):\n{page_text[:4000]}\n\n"
        "Last extract/read_html result (truncated):\n"
        + (last_block[:8000] if last_block else "(none)\n")
    )

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={**payload, "response_format": {"type": "json_object"}},
            )
            if response.status_code >= 400:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.HTTPError:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        data = parse_llm_json(content)
        data["mode"] = "llm"
        return data


def _add_assistant(db: Session, conversation_id: int, content: str) -> None:
    db.add(
        Message(
            conversation_id=conversation_id,
            role=MessageRole.assistant,
            content=content,
        )
    )


def cancel_agent_task(db: Session, task_id: int) -> AgentTask:
    """Mark a pending/running/waiting task cancelled and notify the chat."""
    task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not task:
        raise LookupError("task not found")
    if task.status not in (
        TaskStatus.pending,
        TaskStatus.running,
        TaskStatus.waiting_user,
    ):
        raise ValueError("task not cancellable")

    task.status = TaskStatus.cancelled
    task.waiting_question = None
    append_step(task, {"action": "cancel", "detail": "لغو توسط کاربر"})
    _add_assistant(db, task.conversation_id, "کار لغو شد.")
    db.commit()
    db.refresh(task)
    return task


def _task_was_cancelled(db: Session, task: AgentTask) -> bool:
    db.refresh(task)
    return task.status == TaskStatus.cancelled


async def run_task(db: Session, task_id: int) -> AgentTask:
    task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not task:
        raise ValueError("task not found")
    if task.status == TaskStatus.cancelled:
        return task
    if task.status not in (TaskStatus.pending, TaskStatus.running):
        return task

    # Stay pending while waiting in the single-browser queue so another agent
    # never shares Chromium control (chat + periodic schedules).
    if is_browser_agent_busy():
        append_step(
            task,
            {
                "action": "queued",
                "detail": "در صف کنترل مرورگر — منتظر آزاد شدن ایجنت فعلی",
            },
        )
        db.commit()

    try:
        async with acquire_browser_control(
            task_id,
            is_cancelled=lambda: _task_was_cancelled(db, task),
        ):
            return await _run_task_with_browser(db, task)
    except BrowserControlCancelled:
        db.refresh(task)
        return task


async def _run_task_with_browser(db: Session, task: AgentTask) -> AgentTask:
    """Execute the agent loop while this task holds the browser lock."""
    db.refresh(task)
    if task.status == TaskStatus.cancelled:
        return task
    if task.status not in (TaskStatus.pending, TaskStatus.running):
        return task

    task.status = TaskStatus.running
    task.waiting_question = None
    db.commit()

    browser = BrowserClient()
    history: list[dict[str, Any]] = []
    last_extract = ""
    # Only ever holds actions for the page open in this iteration (replaced on URL change).
    page_actions: list[dict[str, Any]] = []
    page_actions_text = "(none)"
    actions_for_url = ""

    try:
        for _ in range(MAX_STEPS):
            if _task_was_cancelled(db, task):
                return task

            current = await browser.current()
            page_url = current.get("url") or task.current_url or "about:blank"
            page_title = current.get("title") or ""
            try:
                page_text = (await browser.extract("body")).get("text", "")
            except Exception:  # noqa: BLE001
                page_text = ""

            # Interactive tags are scoped to the open page; clear when URL changes.
            if page_url != actions_for_url:
                page_actions = []
                page_actions_text = "(none)"
                actions_for_url = page_url
            try:
                actions_payload = await browser.actions()
                actions_url = actions_payload.get("url") or page_url
                if actions_url != actions_for_url:
                    page_actions = []
                    page_actions_text = "(none)"
                    actions_for_url = actions_url
                    page_url = actions_url
                raw_actions = actions_payload.get("actions") or []
                page_actions = raw_actions if isinstance(raw_actions, list) else []
                page_actions_text = format_page_actions_for_prompt(page_actions)
            except Exception:  # noqa: BLE001
                if page_url != actions_for_url:
                    page_actions = []
                    page_actions_text = "(none)"

            vault_items = list_vault()
            vault_text = format_vault_for_prompt(vault_items)
            schedules_text = format_schedules_for_prompt(list_scheduled_tasks(db))
            chat_memory = load_chat_memory(task.conversation_id)
            # Keep important hrefs from the live page for later turns in this chat.
            if page_actions:
                chat_memory = record_links_from_actions(
                    task.conversation_id,
                    page_url=page_url,
                    page_actions=page_actions,
                )
            chat_memory_text = format_chat_memory_for_prompt(chat_memory)
            cookies_text = format_cookies_file_for_prompt()
            decision = await call_llm_next_action(
                task.instruction,
                page_url,
                page_title,
                page_text,
                history,
                vault_text,
                page_actions_text,
                last_extract,
                schedules_text,
                chat_memory_text,
                cookies_text,
            )
            decision = apply_decision_guardrails(
                decision,
                instruction=task.instruction,
                page_url=page_url,
                page_text=page_text,
                vault_text=vault_text,
                history=history,
                last_extract=last_extract,
                page_actions_text=page_actions_text,
                chat_memory_text=chat_memory_text,
            )
            if _task_was_cancelled(db, task):
                return task

            action = (decision.get("action") or "").lower().strip()
            reason = decision.get("reason") or ""

            if action in {
                "navigate",
                "click",
                "type",
                "press",
                "wait",
                "extract",
                "read_html",
            }:
                try:
                    if action == "navigate":
                        result = await browser.navigate(
                            decision.get("url") or "about:blank"
                        )
                        task.current_url = result.get("url")
                        detail = f"url={task.current_url}"
                        append_step(
                            task,
                            {"action": "navigate", "detail": detail, "reason": reason},
                        )
                        history.append(
                            {"action": "navigate", "detail": detail, "reason": reason}
                        )
                        record_navigate(
                            task.conversation_id,
                            url=str(task.current_url or ""),
                            title=str(result.get("title") or page_title or ""),
                            note=reason or "navigated",
                        )

                    elif action == "click":
                        selector = decision.get("selector") or "body"
                        click_page = page_url
                        result = await browser.click(selector)
                        task.current_url = result.get("url", task.current_url)
                        detail = f"selector={selector}"
                        append_step(
                            task,
                            {"action": "click", "detail": detail, "reason": reason},
                        )
                        history.append(
                            {"action": "click", "detail": detail, "reason": reason}
                        )
                        record_click(
                            task.conversation_id,
                            selector=str(selector),
                            page_url=str(click_page or ""),
                            reason=reason,
                            text=_action_text_for_selector(page_actions, str(selector)),
                        )

                    elif action == "type":
                        selector = decision.get("selector") or "input"
                        text = decision.get("text") or ""
                        type_page = page_url
                        result = await browser.type_text(selector, text)
                        task.current_url = result.get("url", task.current_url)
                        detail = f"selector={selector} | text={text[:120]}"
                        append_step(
                            task,
                            {"action": "type", "detail": detail, "reason": reason},
                        )
                        history.append(
                            {"action": "type", "detail": detail, "reason": reason}
                        )
                        record_field(
                            task.conversation_id,
                            selector=str(selector),
                            page_url=str(type_page or ""),
                            note="typed",
                        )

                    elif action == "press":
                        key = decision.get("key") or "Enter"
                        press_selector = decision.get("selector")
                        result = await browser.press(key, press_selector)
                        task.current_url = result.get("url", task.current_url)
                        detail = (
                            f"key={key}"
                            + (f" | selector={press_selector}" if press_selector else "")
                        )
                        append_step(
                            task,
                            {"action": "press", "detail": detail, "reason": reason},
                        )
                        history.append(
                            {"action": "press", "detail": detail, "reason": reason}
                        )

                    elif action == "wait":
                        ms = int(decision.get("ms") or 1000)
                        result = await browser.wait(ms)
                        task.current_url = result.get("url", task.current_url)
                        append_step(
                            task,
                            {"action": "wait", "detail": f"{ms}ms", "reason": reason},
                        )
                        history.append(
                            {
                                "action": "wait",
                                "detail": f"{ms}ms",
                                "reason": reason,
                            }
                        )

                    elif action == "extract":
                        selector = decision.get("selector") or "body"
                        result = await browser.extract(selector)
                        last_extract = (result.get("text") or "")[:2000]
                        task.current_url = result.get("url", task.current_url)
                        detail = f"selector={selector} | text={last_extract[:160]}"
                        append_step(
                            task,
                            {"action": "extract", "detail": detail, "reason": reason},
                        )
                        history.append(
                            {"action": "extract", "detail": detail, "reason": reason}
                        )

                    elif action == "read_html":
                        selector = str(decision.get("selector") or "html").strip() or "html"
                        query = decision.get("query")
                        query_s = str(query).strip() if query is not None else ""
                        result = await browser.read_html(
                            selector=selector,
                            query=query_s or None,
                            max_chars=60000,
                        )
                        html = (result.get("html") or "")[:12000]
                        mode = result.get("mode") or "full"
                        matches = result.get("matches") or 0
                        truncated = bool(result.get("truncated"))
                        last_extract = (
                            f"[read_html mode={mode} selector={selector}"
                            f"{' query=' + query_s if query_s else ''}"
                            f" matches={matches} truncated={truncated}]\n"
                            f"{html}"
                        )
                        task.current_url = result.get("url", task.current_url)
                        detail = (
                            f"{mode} sel={selector}"
                            + (f" q={query_s[:40]}" if query_s else "")
                            + f" matches={matches} len={len(html)}"
                        )
                        append_step(
                            task,
                            {
                                "action": "read_html",
                                "detail": detail,
                                "reason": reason,
                            },
                        )
                        history.append(
                            {
                                "action": "read_html",
                                "detail": detail + "\n" + html[:500],
                                "reason": reason,
                            }
                        )
                except Exception as action_exc:  # noqa: BLE001
                    err = str(action_exc)[:300]
                    append_step(
                        task,
                        {
                            "action": f"{action}_error",
                            "detail": err,
                            "reason": reason,
                        },
                    )
                    history.append(
                        {
                            "action": f"{action}_error",
                            "detail": err,
                            "reason": reason,
                        }
                    )
                    db.commit()
                    continue

            elif action == "list_cookies":
                domain_filter = str(decision.get("domain") or "").strip() or None
                try:
                    result = await browser.list_cookies(domain_filter)
                except Exception as cookie_exc:  # noqa: BLE001
                    detail = str(cookie_exc)[:300]
                    append_step(
                        task,
                        {
                            "action": "list_cookies_error",
                            "detail": detail,
                            "reason": reason,
                        },
                    )
                    history.append(
                        {
                            "action": "list_cookies_error",
                            "detail": detail,
                            "reason": reason,
                        }
                    )
                    db.commit()
                    continue
                cookies = result.get("cookies") or []
                lines: list[str] = []
                for row in cookies[:50]:
                    if not isinstance(row, dict):
                        continue
                    val = str(row.get("value") or "")
                    if len(val) > 40:
                        val = val[:20] + "…" + val[-8:]
                    lines.append(
                        f"{row.get('name')}|{row.get('domain')}|{row.get('path')}|{val}"
                    )
                detail = (
                    f"count={result.get('count', len(cookies))} "
                    f"file={result.get('path') or COOKIES_FILE}\n"
                    + ("\n".join(lines) if lines else "(none)")
                )
                last_extract = detail[:4000]
                append_step(
                    task,
                    {"action": "list_cookies", "detail": detail[:500], "reason": reason},
                )
                history.append(
                    {"action": "list_cookies", "detail": detail[:800], "reason": reason}
                )

            elif action == "set_cookie":
                name = str(decision.get("name") or "").strip()
                value = str(decision.get("value") or "")
                domain = str(decision.get("domain") or "").strip()
                if not name or not domain:
                    task.status = TaskStatus.waiting_user
                    task.waiting_question = (
                        "برای set_cookie باید name و domain را مشخص کنید "
                        "(value هم لازم است)."
                    )
                    append_step(
                        task,
                        {
                            "action": "set_cookie_ask",
                            "detail": task.waiting_question,
                            "reason": reason or "missing_fields",
                        },
                    )
                    _add_assistant(db, task.conversation_id, task.waiting_question)
                    db.commit()
                    db.refresh(task)
                    return task
                path = str(decision.get("path") or "/") or "/"
                same_site = decision.get("sameSite") or decision.get("same_site") or "Lax"
                expires = decision.get("expires")
                try:
                    result = await browser.set_cookie(
                        name=name,
                        value=value,
                        domain=domain,
                        path=path,
                        expires=expires,
                        http_only=bool(
                            decision.get("httpOnly") or decision.get("http_only")
                        ),
                        secure=bool(decision.get("secure")),
                        same_site=str(same_site) if same_site is not None else "Lax",
                        url=str(decision.get("url") or "").strip() or None,
                    )
                except Exception as cookie_exc:  # noqa: BLE001
                    detail = str(cookie_exc)[:300]
                    append_step(
                        task,
                        {
                            "action": "set_cookie_error",
                            "detail": detail,
                            "reason": reason,
                        },
                    )
                    history.append(
                        {
                            "action": "set_cookie_error",
                            "detail": detail,
                            "reason": reason,
                        }
                    )
                    db.commit()
                    continue
                detail = (
                    f"set name={name} domain={domain} path={path} "
                    f"file={result.get('path') or COOKIES_FILE} "
                    f"count={result.get('count')}"
                )
                append_step(
                    task,
                    {"action": "set_cookie", "detail": detail, "reason": reason},
                )
                history.append(
                    {"action": "set_cookie", "detail": detail, "reason": reason}
                )

            elif action == "delete_cookie":
                name = str(decision.get("name") or "").strip()
                if not name:
                    task.status = TaskStatus.waiting_user
                    task.waiting_question = "برای delete_cookie باید name کوکی را بدهید."
                    append_step(
                        task,
                        {
                            "action": "delete_cookie_ask",
                            "detail": task.waiting_question,
                            "reason": reason or "missing_name",
                        },
                    )
                    _add_assistant(db, task.conversation_id, task.waiting_question)
                    db.commit()
                    db.refresh(task)
                    return task
                domain = str(decision.get("domain") or "").strip() or None
                path = str(decision.get("path") or "").strip() or None
                try:
                    result = await browser.delete_cookie(
                        name=name, domain=domain, path=path
                    )
                except Exception as cookie_exc:  # noqa: BLE001
                    detail = str(cookie_exc)[:300]
                    append_step(
                        task,
                        {
                            "action": "delete_cookie_error",
                            "detail": detail,
                            "reason": reason,
                        },
                    )
                    history.append(
                        {
                            "action": "delete_cookie_error",
                            "detail": detail,
                            "reason": reason,
                        }
                    )
                    db.commit()
                    continue
                detail = (
                    f"deleted name={name} domain={domain or '*'} "
                    f"removed={result.get('removed')} "
                    f"file={result.get('path') or COOKIES_FILE}"
                )
                append_step(
                    task,
                    {"action": "delete_cookie", "detail": detail, "reason": reason},
                )
                history.append(
                    {"action": "delete_cookie", "detail": detail, "reason": reason}
                )

            elif action == "save_credential":
                item = save_vault_item(
                    label=str(decision.get("label") or ""),
                    site_url=str(decision.get("site_url") or page_url or ""),
                    username=str(decision.get("username") or ""),
                    secret_note=str(decision.get("secret_note") or ""),
                )
                detail = f"id={item.get('id')} label={item.get('label')} file={CREDENTIALS_FILE}"
                append_step(
                    task,
                    {"action": "save_credential", "detail": detail, "reason": reason},
                )
                history.append(
                    {"action": "save_credential", "detail": detail, "reason": reason}
                )

            elif action == "schedule_periodic_task":
                title = str(decision.get("title") or "").strip()
                steps = str(decision.get("steps") or "").strip()
                raw_interval = decision.get("interval_minutes")
                run_immediately = bool(decision.get("run_immediately") or False)
                try:
                    interval_ok = int(raw_interval) >= 5
                except (TypeError, ValueError):
                    interval_ok = False
                if not title or not steps or not interval_ok:
                    task.status = TaskStatus.waiting_user
                    task.waiting_question = (
                        "برای کار دوره‌ای عنوان، فاصلهٔ زمانی (حداقل ۵ دقیقه) "
                        "و مراحل دقیق را مشخص کنید. در مراحل برای هر کلیک/تایپ، "
                        "selector یا متن دکمه و URL را بنویسید."
                    )
                    append_step(
                        task,
                        {
                            "action": "schedule_periodic_task_ask",
                            "detail": task.waiting_question,
                            "reason": reason or "missing_fields",
                        },
                    )
                    _add_assistant(db, task.conversation_id, task.waiting_question)
                    db.commit()
                    db.refresh(task)
                    return task
                try:
                    scheduled = create_scheduled_task(
                        db,
                        title=title,
                        interval_minutes=int(raw_interval),
                        steps=steps,
                        run_immediately=run_immediately,
                        source_instruction=task.instruction or "",
                        page_url=page_url or "",
                        page_title=page_title or "",
                        action_history=list(history),
                        page_actions=list(page_actions),
                    )
                except ValueError as exc:
                    task.status = TaskStatus.waiting_user
                    msg = str(exc)
                    if "too vague" in msg or "steps" in msg.lower():
                        task.waiting_question = (
                            "مراحل کار دوره‌ای خیلی کلی است. لطفاً مراحل شماره‌دار با "
                            "URL و selector/متن دکمه بنویسید؛ مثلاً:\n"
                            "1) navigate → url=…\n"
                            "2) click → selector=… | text=…\n"
                            "3) type → selector=… | text=…"
                        )
                    else:
                        task.waiting_question = f"ثبت کار دوره‌ای ممکن نشد: {exc}"
                    append_step(
                        task,
                        {
                            "action": "schedule_periodic_task_error",
                            "detail": str(exc),
                            "reason": reason,
                        },
                    )
                    _add_assistant(db, task.conversation_id, task.waiting_question)
                    db.commit()
                    db.refresh(task)
                    return task
                detail = (
                    f"id={scheduled.id} every={scheduled.interval_minutes}m "
                    f"next={scheduled.next_run_at} file={scheduled.steps_file}"
                )
                append_step(
                    task,
                    {
                        "action": "schedule_periodic_task",
                        "detail": detail,
                        "reason": reason,
                    },
                )
                history.append(
                    {
                        "action": "schedule_periodic_task",
                        "detail": detail,
                        "reason": reason,
                    }
                )

            elif action == "ask":
                if _task_was_cancelled(db, task):
                    return task
                task.status = TaskStatus.waiting_user
                task.waiting_question = (
                    decision.get("question") or "برای ادامه راهنمایی کنید."
                )
                append_step(
                    task,
                    {"action": "ask", "detail": task.waiting_question, "reason": reason},
                )
                _add_assistant(db, task.conversation_id, task.waiting_question)
                db.commit()
                db.refresh(task)
                return task

            elif action == "done":
                if _task_was_cancelled(db, task):
                    return task
                summary = (
                    decision.get("summary")
                    or last_extract
                    or "کار انجام شد."
                )
                task.summary = summary[:2000]
                task.current_url = (await browser.current()).get("url", task.current_url)
                task.status = TaskStatus.completed
                append_step(
                    task, {"action": "done", "detail": "کار تمام شد", "reason": reason}
                )
                _add_assistant(db, task.conversation_id, task.summary)
                db.commit()
                db.refresh(task)
                return task

            else:
                if _task_was_cancelled(db, task):
                    return task
                append_step(
                    task,
                    {
                        "action": "unknown",
                        "detail": action or "empty",
                        "reason": reason,
                    },
                )
                history.append({"action": "unknown", "detail": action, "reason": reason})
                task.status = TaskStatus.waiting_user
                task.waiting_question = (
                    "ایجنت پاسخ نامشخصی از مدل گرفت. چطور ادامه بدهم؟"
                )
                _add_assistant(db, task.conversation_id, task.waiting_question)
                db.commit()
                db.refresh(task)
                return task

            db.commit()

        if _task_was_cancelled(db, task):
            return task

        extract = await browser.extract("body")
        task.current_url = (await browser.current()).get("url", task.current_url)
        task.summary = (last_extract or extract.get("text") or "سقف مراحل ایجنت تمام شد.")[
            :2000
        ]
        task.status = TaskStatus.completed
        append_step(task, {"action": "done", "detail": "سقف مراحل"})
        _add_assistant(db, task.conversation_id, task.summary[:800])
        db.commit()
    except Exception as exc:  # noqa: BLE001
        if _task_was_cancelled(db, task):
            return task
        task.status = TaskStatus.waiting_user
        task.waiting_question = (
            f"خطا رخ داد: {exc}. چطور ادامه بدهم؟ می‌توانید راهنمایی کنید یا کار را لغو کنید."
        )
        append_step(task, {"action": "error", "detail": str(exc)})
        _add_assistant(db, task.conversation_id, task.waiting_question)
        db.commit()

    db.refresh(task)
    return task
