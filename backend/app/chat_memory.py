"""Per-conversation agent memory on shared browser_data volume.

Stores important URLs, clicked controls, typed fields, and key links so later
steps in the same chat (and future tasks) can reuse evidenced selectors/URLs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHAT_MEMORY_DIR = Path("/data/browser/chat_memory")
MAX_URLS = 40
MAX_CLICKS = 60
MAX_FIELDS = 40
MAX_LINKS = 60
MAX_NOTES = 30


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def memory_path(conversation_id: int) -> Path:
    return CHAT_MEMORY_DIR / f"{int(conversation_id)}.json"


def _empty(conversation_id: int) -> dict[str, Any]:
    return {
        "conversation_id": int(conversation_id),
        "updated_at": utcnow_iso(),
        "urls": [],
        "clicks": [],
        "fields": [],
        "links": [],
        "notes": [],
    }


def load_chat_memory(conversation_id: int) -> dict[str, Any]:
    path = memory_path(conversation_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty(conversation_id)
    if not isinstance(raw, dict):
        return _empty(conversation_id)
    data = _empty(conversation_id)
    for key in ("urls", "clicks", "fields", "links", "notes"):
        val = raw.get(key)
        if isinstance(val, list):
            data[key] = val
    data["updated_at"] = str(raw.get("updated_at") or data["updated_at"])
    return data


def save_chat_memory(conversation_id: int, data: dict[str, Any]) -> str:
    CHAT_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    path = memory_path(conversation_id)
    payload = dict(data or _empty(conversation_id))
    payload["conversation_id"] = int(conversation_id)
    payload["updated_at"] = utcnow_iso()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def delete_chat_memory(conversation_id: int) -> None:
    try:
        memory_path(conversation_id).unlink(missing_ok=True)
    except OSError:
        pass


def _dedupe_append(items: list[dict[str, Any]], key_fields: tuple[str, ...], row: dict[str, Any], *, limit: int) -> None:
    key = tuple((row.get(k) or "").strip() for k in key_fields)
    if not any(key):
        return
    for existing in items:
        existing_key = tuple((existing.get(k) or "").strip() for k in key_fields)
        if existing_key == key:
            existing.update({k: v for k, v in row.items() if v not in (None, "")})
            return
    items.append(row)
    while len(items) > limit:
        items.pop(0)


def record_navigate(
    conversation_id: int,
    *,
    url: str,
    title: str = "",
    note: str = "",
) -> dict[str, Any]:
    data = load_chat_memory(conversation_id)
    _dedupe_append(
        data["urls"],
        ("url",),
        {
            "url": (url or "").strip()[:1024],
            "title": (title or "").strip()[:255],
            "note": (note or "navigated").strip()[:255],
            "at": utcnow_iso(),
        },
        limit=MAX_URLS,
    )
    save_chat_memory(conversation_id, data)
    return data


def record_click(
    conversation_id: int,
    *,
    selector: str,
    page_url: str = "",
    reason: str = "",
    text: str = "",
) -> dict[str, Any]:
    data = load_chat_memory(conversation_id)
    _dedupe_append(
        data["clicks"],
        ("selector", "page_url"),
        {
            "selector": (selector or "").strip()[:500],
            "page_url": (page_url or "").strip()[:1024],
            "text": (text or "").strip()[:120],
            "reason": (reason or "").strip()[:255],
            "at": utcnow_iso(),
        },
        limit=MAX_CLICKS,
    )
    save_chat_memory(conversation_id, data)
    return data


def record_field(
    conversation_id: int,
    *,
    selector: str,
    page_url: str = "",
    note: str = "",
) -> dict[str, Any]:
    data = load_chat_memory(conversation_id)
    _dedupe_append(
        data["fields"],
        ("selector", "page_url"),
        {
            "selector": (selector or "").strip()[:500],
            "page_url": (page_url or "").strip()[:1024],
            "note": (note or "typed").strip()[:255],
            "at": utcnow_iso(),
        },
        limit=MAX_FIELDS,
    )
    save_chat_memory(conversation_id, data)
    return data


def record_links_from_actions(
    conversation_id: int,
    *,
    page_url: str,
    page_actions: list[dict[str, Any]] | None,
    limit: int = 12,
) -> dict[str, Any]:
    """Capture important hrefs from the current page actions snapshot."""
    if not page_actions:
        return load_chat_memory(conversation_id)
    data = load_chat_memory(conversation_id)
    added = 0
    for item in page_actions:
        if added >= limit:
            break
        kind = (item.get("kind") or "").strip().lower()
        href = (item.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue
        if kind not in {"link", "button", "form", ""} and not href.startswith("http"):
            continue
        if not href.startswith(("http://", "https://", "/")):
            continue
        _dedupe_append(
            data["links"],
            ("href", "page_url"),
            {
                "href": href[:1024],
                "text": (item.get("text") or "").strip()[:120],
                "selector": (item.get("selector") or "").strip()[:500],
                "kind": kind or "link",
                "page_url": (page_url or "").strip()[:1024],
                "at": utcnow_iso(),
            },
            limit=MAX_LINKS,
        )
        added += 1
    save_chat_memory(conversation_id, data)
    return data


def record_note(conversation_id: int, note: str) -> dict[str, Any]:
    text = (note or "").strip()
    if not text:
        return load_chat_memory(conversation_id)
    data = load_chat_memory(conversation_id)
    notes: list[Any] = data.get("notes") or []
    if text not in notes:
        notes.append(text[:500])
    data["notes"] = notes[-MAX_NOTES:]
    save_chat_memory(conversation_id, data)
    return data


def format_chat_memory_for_prompt(data: dict[str, Any] | None, *, max_chars: int = 3500) -> str:
    if not data:
        return "(empty — no chat memory yet)"
    lines: list[str] = [
        f"file=/data/browser/chat_memory/{data.get('conversation_id')}.json",
        f"updated_at={data.get('updated_at') or '-'}",
    ]

    urls = data.get("urls") or []
    if urls:
        lines.append("Important URLs:")
        for row in urls[-15:]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- url={row.get('url') or '-'} | title={row.get('title') or '-'} | "
                f"note={row.get('note') or '-'}"
            )

    clicks = data.get("clicks") or []
    if clicks:
        lines.append("Clicked controls (reuse selector when same page):")
        for row in clicks[-20:]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- selector={row.get('selector') or '-'} | page={row.get('page_url') or '-'} | "
                f"text={row.get('text') or '-'} | reason={row.get('reason') or '-'}"
            )

    fields = data.get("fields") or []
    if fields:
        lines.append("Typed fields:")
        for row in fields[-15:]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- selector={row.get('selector') or '-'} | page={row.get('page_url') or '-'} | "
                f"note={row.get('note') or '-'}"
            )

    links = data.get("links") or []
    if links:
        lines.append("Important links seen:")
        for row in links[-20:]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- href={row.get('href') or '-'} | text={row.get('text') or '-'} | "
                f"selector={row.get('selector') or '-'} | page={row.get('page_url') or '-'}"
            )

    notes = data.get("notes") or []
    if notes:
        lines.append("Notes:")
        for note in notes[-10:]:
            lines.append(f"- {note}")

    if len(lines) <= 2:
        return "(empty — no chat memory yet)"
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text
