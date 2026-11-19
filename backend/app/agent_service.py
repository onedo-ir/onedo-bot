import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.browser_client import BrowserClient
from app.config import get_settings
from app.models import AgentTask, Message, MessageRole, TaskStatus

MAX_STEPS = 15
# Persistent file vault (no panel UI / no DB table). Shared browser_data volume.
CREDENTIALS_FILE = Path("/data/browser/credentials.json")

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
) -> str:
    parts = [instruction, page_url, page_text, vault_text, last_extract, page_actions_text]
    for item in history[-12:]:
        parts.append(str(item.get("detail") or ""))
        parts.append(str(item.get("reason") or ""))
        parts.append(str(item.get("action") or ""))
    return _norm("\n".join(parts))


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
        "save_credential|ask|done\n"
        "  url (navigate), selector (click/type/extract/read_html), text (type),\n"
        "  query (optional search string for read_html),\n"
        "  key (press, e.g. Enter), ms (wait), question (ask),\n"
        "  label/site_url/username/secret_note (save_credential),\n"
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
        "12) Pure Q&A with no browsing needed → done with a Persian answer.\n"
        "13) When interactive list/text is not enough to find a control or structure, "
        "use read_html (optionally with query=keyword) to inspect cleaned HTML and "
        "derive a real selector from it — then click/type. Prefer query search over "
        "dumping the whole page when you know a keyword.\n"
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


async def run_task(db: Session, task_id: int) -> AgentTask:
    task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not task:
        raise ValueError("task not found")

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
            decision = await call_llm_next_action(
                task.instruction,
                page_url,
                page_title,
                page_text,
                history,
                vault_text,
                page_actions_text,
                last_extract,
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
            )
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
                        detail = task.current_url
                        append_step(
                            task,
                            {"action": "navigate", "detail": detail, "reason": reason},
                        )
                        history.append(
                            {"action": "navigate", "detail": detail, "reason": reason}
                        )

                    elif action == "click":
                        selector = decision.get("selector") or "body"
                        result = await browser.click(selector)
                        task.current_url = result.get("url", task.current_url)
                        append_step(
                            task,
                            {"action": "click", "detail": selector, "reason": reason},
                        )
                        history.append(
                            {"action": "click", "detail": selector, "reason": reason}
                        )

                    elif action == "type":
                        selector = decision.get("selector") or "input"
                        text = decision.get("text") or ""
                        result = await browser.type_text(selector, text)
                        task.current_url = result.get("url", task.current_url)
                        detail = text[:80]
                        append_step(
                            task,
                            {"action": "type", "detail": detail, "reason": reason},
                        )
                        history.append(
                            {"action": "type", "detail": detail, "reason": reason}
                        )

                    elif action == "press":
                        key = decision.get("key") or "Enter"
                        result = await browser.press(key, decision.get("selector"))
                        task.current_url = result.get("url", task.current_url)
                        append_step(
                            task,
                            {"action": "press", "detail": key, "reason": reason},
                        )
                        history.append(
                            {"action": "press", "detail": key, "reason": reason}
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
                        detail = last_extract[:120]
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

            elif action == "ask":
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
        task.status = TaskStatus.waiting_user
        task.waiting_question = (
            f"خطا رخ داد: {exc}. چطور ادامه بدهم؟ می‌توانید راهنمایی کنید یا کار را لغو کنید."
        )
        append_step(task, {"action": "error", "detail": str(exc)})
        _add_assistant(db, task.conversation_id, task.waiting_question)
        db.commit()

    db.refresh(task)
    return task
