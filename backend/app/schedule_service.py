"""Periodic scheduled agent tasks: steps files on volume + DB rows + runner."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AgentTask, Conversation, Message, MessageRole, ScheduledTask, TaskStatus

SCHEDULED_DIR = Path("/data/browser/scheduled_tasks")
MIN_INTERVAL_MINUTES = 5
MAX_INTERVAL_MINUTES = 60 * 24 * 30  # 30 days
SCHEDULER_POLL_SECONDS = 30
MIN_STEPS_CHARS = 80
# Cap how many agent jobs may sit pending/running before we defer new due spawns.
# Prevents unbounded queue growth when the browser lock is held for a long time.
MAX_AGENT_QUEUE_DEPTH = 20

_scheduler_task: asyncio.Task | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def clamp_interval_minutes(value: Any) -> int:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        minutes = 0
    return max(MIN_INTERVAL_MINUTES, min(MAX_INTERVAL_MINUTES, minutes))


def steps_file_path(schedule_id: int) -> Path:
    return SCHEDULED_DIR / f"{schedule_id}.md"


def steps_look_detailed(steps: str) -> bool:
    """Reject vague one-liners so the future agent has something actionable."""
    text = (steps or "").strip()
    if len(text) < MIN_STEPS_CHARS:
        return False
    lowered = text.lower()
    markers = (
        "navigate",
        "click",
        "type",
        "press",
        "selector",
        "http://",
        "https://",
        "url",
        "کلیک",
        "برو به",
        "باز کن",
        "وارد",
        "فیلد",
        "دکمه",
        "صفحه",
        "مرحله",
    )
    return sum(1 for m in markers if m in lowered or m in text) >= 2


def _format_history_block(action_history: list[dict[str, Any]] | None) -> str:
    if not action_history:
        return "(در این جلسه هنوز اکشن مرورگری ثبت نشده)"
    lines: list[str] = []
    for idx, item in enumerate(action_history, 1):
        action = str(item.get("action") or "?").strip()
        detail = str(item.get("detail") or "").strip()
        reason = str(item.get("reason") or "").strip()
        # Keep playbook readable; avoid dumping huge HTML from read_html.
        if action == "read_html" and "\n" in detail:
            detail = detail.split("\n", 1)[0].strip()
        detail = detail[:400]
        line = f"{idx}. `{action}` → {detail or '(بدون جزئیات)'}"
        if reason:
            line += f"\n   دلیل: {reason[:200]}"
        lines.append(line)
    return "\n".join(lines)


def _format_page_actions_block(page_actions: list[dict[str, Any]] | None, *, limit: int = 40) -> str:
    if not page_actions:
        return "(لیست عناصر تعاملی هنگام ثبت خالی بود)"
    lines: list[str] = []
    for item in page_actions[:limit]:
        kind = (item.get("kind") or "control").strip()
        tag = (item.get("tag") or "?").strip()
        text = (item.get("text") or "").strip()[:80]
        href = (item.get("href") or "").strip()[:220]
        typ = (item.get("type") or "").strip()
        name = (item.get("name") or "").strip()
        selector = (item.get("selector") or "").strip()
        parts = [f"[{kind}]", tag]
        if text:
            parts.append(f'text="{text}"')
        if href:
            parts.append(f'href="{href}"')
        if typ:
            parts.append(f"type={typ}")
        if name:
            parts.append(f"name={name}")
        if selector:
            parts.append(f"selector=`{selector}`")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)


def build_playbook_markdown(
    *,
    title: str,
    interval_minutes: int,
    steps: str,
    source_instruction: str = "",
    page_url: str = "",
    page_title: str = "",
    action_history: list[dict[str, Any]] | None = None,
    page_actions: list[dict[str, Any]] | None = None,
) -> str:
    """Rich markdown playbook so a future agent run knows exact clicks/URLs."""
    title_s = (title or "").strip() or "کار دوره‌ای"
    body = (steps or "").strip() or "(مراحل مشخص نشده)"
    created = utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    src = (source_instruction or "").strip()
    if len(src) > 4000:
        src = src[:4000] + "\n…"

    return (
        f"# {title_s}\n\n"
        f"- interval_minutes: `{interval_minutes}`\n"
        f"- created_at: `{created}`\n"
        f"- page_url_at_schedule: `{page_url or 'about:blank'}`\n"
        f"- page_title_at_schedule: {(page_title or '-').strip() or '-'}\n\n"
        "## دستورالعمل اجرا برای ایجنت\n\n"
        "این فایل **playbook کار دوره‌ای** است. مراحل را به‌ترتیب انجام بده.\n"
        "- از همان `URL` و `selector`های ذکرشده استفاده کن.\n"
        "- قبل از هر کلیک/تایپ، لیست عناصر تعاملی **صفحهٔ فعلی** را چک کن؛ "
        "اگر selector قدیمی نبود، کنترل هم‌معنی (همان text/href/name) را از لیست فعلی بگیر.\n"
        "- اگر صفحه یا کنترل پیدا نشد، **حدس نزن** — `ask` کن یا `extract`/`read_html`.\n"
        "- Google را باز نکن مگر playbook صریحاً گفته باشد.\n\n"
        "## هدف / درخواست اصلی کاربر\n\n"
        f"{src or '(ثبت نشده)'}\n\n"
        "## شواهد جلسهٔ ثبت (مسیر واقعی ایجنت)\n\n"
        "این بخش نشان می‌دهد قبلاً کجا رفته و روی چه چیزهایی کار شده؛ "
        "برای بازتولید همان مسیر از آن استفاده کن.\n\n"
        f"{_format_history_block(action_history)}\n\n"
        "## کنترل‌های مهم صفحه هنگام ثبت\n\n"
        "اگر در مراحل زیر selector دقیق نبود، از این فهرست (text/href/selector) کمک بگیر:\n\n"
        f"{_format_page_actions_block(page_actions)}\n\n"
        "## مراحل دقیق اجرا\n\n"
        "هر مرحله باید یکی از اکشن‌های مرورگر باشد "
        "(`navigate` / `click` / `type` / `press` / `wait` / `extract` / `read_html`) "
        "با URL یا selector مشخص.\n\n"
        f"{body}\n\n"
        "## معیار موفقیت\n\n"
        "- وقتی همهٔ مراحل playbook انجام شد و نتیجهٔ قابل‌مشاهده روی صفحه تأیید شد → `done` با خلاصهٔ فارسی.\n"
        "- اگر مانع ورود/کپچا/OTP بود و در credentials یا playbook نبود → `ask`.\n"
    )


def write_steps_file(
    schedule_id: int,
    *,
    title: str,
    interval_minutes: int,
    steps: str,
    source_instruction: str = "",
    page_url: str = "",
    page_title: str = "",
    action_history: list[dict[str, Any]] | None = None,
    page_actions: list[dict[str, Any]] | None = None,
) -> str:
    SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
    path = steps_file_path(schedule_id)
    content = build_playbook_markdown(
        title=title,
        interval_minutes=interval_minutes,
        steps=steps,
        source_instruction=source_instruction,
        page_url=page_url,
        page_title=page_title,
        action_history=action_history,
        page_actions=page_actions,
    )
    path.write_text(content, encoding="utf-8")
    return str(path)


def read_steps_file(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def delete_steps_file(path: str | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def format_schedules_for_prompt(items: list[ScheduledTask]) -> str:
    if not items:
        return "(none)"
    lines: list[str] = []
    for row in items:
        lines.append(
            f"- id={row.id} | title={row.title} | every={row.interval_minutes}m | "
            f"enabled={row.enabled} | next={row.next_run_at} | file={row.steps_file}"
        )
    return "\n".join(lines)


def create_scheduled_task(
    db: Session,
    *,
    title: str,
    interval_minutes: int,
    steps: str,
    run_immediately: bool = False,
    source_instruction: str = "",
    page_url: str = "",
    page_title: str = "",
    action_history: list[dict[str, Any]] | None = None,
    page_actions: list[dict[str, Any]] | None = None,
) -> ScheduledTask:
    title_s = (title or "").strip()[:255] or "کار دوره‌ای"
    minutes = clamp_interval_minutes(interval_minutes)
    steps_s = (steps or "").strip()
    if not steps_s:
        raise ValueError("steps required")
    if not steps_look_detailed(steps_s):
        raise ValueError(
            "steps too vague — include numbered browser actions with URLs/selectors "
            "(navigate/click/type/…)"
        )

    now = utcnow()
    next_run = now if run_immediately else now + timedelta(minutes=minutes)
    row = ScheduledTask(
        title=title_s,
        interval_minutes=minutes,
        steps_file="",
        enabled=True,
        next_run_at=next_run,
    )
    db.add(row)
    db.flush()
    row.steps_file = write_steps_file(
        row.id,
        title=title_s,
        interval_minutes=minutes,
        steps=steps_s,
        source_instruction=source_instruction,
        page_url=page_url,
        page_title=page_title,
        action_history=action_history,
        page_actions=page_actions,
    )
    db.commit()
    db.refresh(row)
    return row


def delete_scheduled_task(db: Session, schedule_id: int) -> None:
    row = db.query(ScheduledTask).filter(ScheduledTask.id == schedule_id).first()
    if not row:
        raise LookupError("scheduled task not found")
    delete_steps_file(row.steps_file)
    # also remove by convention path if steps_file was empty/wrong
    delete_steps_file(str(steps_file_path(schedule_id)))
    db.delete(row)
    db.commit()


def list_scheduled_tasks(db: Session, *, limit: int = 200) -> list[ScheduledTask]:
    return (
        db.query(ScheduledTask)
        .order_by(ScheduledTask.created_at.desc())
        .limit(limit)
        .all()
    )


async def _run_task_background(task_id: int) -> None:
    from app.agent_service import run_task

    db = SessionLocal()
    try:
        # run_task acquires the shared browser lock; multiple due jobs queue FIFO.
        await run_task(db, task_id)
    finally:
        db.close()


def _active_statuses() -> tuple[TaskStatus, ...]:
    return (TaskStatus.pending, TaskStatus.running, TaskStatus.waiting_user)


def _pending_or_running_count(db: Session) -> int:
    return (
        db.query(AgentTask)
        .filter(AgentTask.status.in_((TaskStatus.pending, TaskStatus.running)))
        .count()
    )


def _spawn_run_for_schedule(db: Session, sched: ScheduledTask, now: datetime) -> int | None:
    """Create conversation+task for a due schedule. Returns new task id or None if skipped.

    Skips if this schedule's previous run is still active. New tasks enter the
    global browser queue (see browser_agent_lock) so they never control Chromium
    concurrently with another agent.
    """
    if sched.last_task_id:
        last = db.query(AgentTask).filter(AgentTask.id == sched.last_task_id).first()
        if last and last.status in _active_statuses():
            return None

    steps = read_steps_file(sched.steps_file)
    if steps:
        instruction = (
            f"کار دوره‌ای «{sched.title}» — playbook زیر را دقیق دنبال کن.\n"
            f"فاصلهٔ زمان‌بندی: هر {sched.interval_minutes} دقیقه.\n\n"
            f"{steps}"
        )
    else:
        instruction = (
            f"کار دوره‌ای: {sched.title}\n\n"
            f"(فایل مراحل در دسترس نبود؛ طبق عنوان و دانش قبلی انجام بده — حدس نزن.)"
        )

    conv = Conversation(title=f"[دوره‌ای] {sched.title}"[:255])
    db.add(conv)
    db.flush()
    db.add(
        Message(
            conversation_id=conv.id,
            role=MessageRole.user,
            content=instruction[:20000],
        )
    )
    task = AgentTask(
        conversation_id=conv.id,
        instruction=instruction[:20000],
        status=TaskStatus.pending,
    )
    db.add(task)
    db.flush()

    sched.last_run_at = now
    sched.last_task_id = task.id
    sched.next_run_at = now + timedelta(minutes=max(sched.interval_minutes, MIN_INTERVAL_MINUTES))
    db.commit()
    return task.id


async def tick_due_schedules() -> int:
    """Enqueue due periodic tasks. Returns number of spawned runs.

    Spawns even when another agent holds the browser; ``run_task`` waits on the
    shared lock so only one agent drives Chromium. ``next_run_at`` advances on
    spawn so a long queue does not create duplicate due firings for the same row.
    If the pending/running agent queue is already deep, defer (leave next_run_at)
    until the browser drain makes room.
    """
    db = SessionLocal()
    started = 0
    try:
        if _pending_or_running_count(db) >= MAX_AGENT_QUEUE_DEPTH:
            return 0

        now = utcnow()
        due = (
            db.query(ScheduledTask)
            .filter(
                ScheduledTask.enabled.is_(True),
                ScheduledTask.next_run_at <= now,
            )
            .order_by(ScheduledTask.next_run_at.asc())
            .limit(20)
            .all()
        )
        task_ids: list[int] = []
        for sched in due:
            if _pending_or_running_count(db) >= MAX_AGENT_QUEUE_DEPTH:
                break
            task_id = _spawn_run_for_schedule(db, sched, now)
            if task_id is not None:
                task_ids.append(task_id)
                started += 1
        for task_id in task_ids:
            asyncio.create_task(_run_task_background(task_id))
    finally:
        db.close()
    return started


async def _scheduler_loop() -> None:
    while True:
        try:
            await tick_due_schedules()
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(SCHEDULER_POLL_SECONDS)


async def start_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop())


async def stop_scheduler() -> None:
    global _scheduler_task
    task = _scheduler_task
    _scheduler_task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
