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


def write_steps_file(
    schedule_id: int,
    *,
    title: str,
    interval_minutes: int,
    steps: str,
) -> str:
    SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
    path = steps_file_path(schedule_id)
    body = (steps or "").strip() or "(مراحل مشخص نشده)"
    content = (
        f"# {title.strip() or 'کار دوره‌ای'}\n\n"
        f"interval_minutes: {interval_minutes}\n\n"
        f"## مراحل اجرا\n\n"
        f"{body}\n"
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
) -> ScheduledTask:
    title_s = (title or "").strip()[:255] or "کار دوره‌ای"
    minutes = clamp_interval_minutes(interval_minutes)
    steps_s = (steps or "").strip()
    if not steps_s:
        raise ValueError("steps required")

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
        await run_task(db, task_id)
    finally:
        db.close()


def _active_statuses() -> tuple[TaskStatus, ...]:
    return (TaskStatus.pending, TaskStatus.running, TaskStatus.waiting_user)


def _spawn_run_for_schedule(db: Session, sched: ScheduledTask, now: datetime) -> int | None:
    """Create conversation+task for a due schedule. Returns new task id or None if skipped."""
    if sched.last_task_id:
        last = db.query(AgentTask).filter(AgentTask.id == sched.last_task_id).first()
        if last and last.status in _active_statuses():
            return None

    steps = read_steps_file(sched.steps_file)
    instruction = steps or (
        f"کار دوره‌ای: {sched.title}\n\n"
        f"(فایل مراحل در دسترس نبود؛ طبق عنوان و دانش قبلی انجام بده.)"
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
    """Start due periodic tasks. Returns number of started runs."""
    db = SessionLocal()
    started = 0
    try:
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
