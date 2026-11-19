"""Single-browser agent mutex: only one run_task controls Chromium at a time.

Chat agents and periodic schedules share one asyncio queue/lock so concurrent
runs cannot interleave clicks/navigation on the shared Playwright browser.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

# Fair mutex among agent runs in this process (backend is single-worker).
_lock = asyncio.Lock()
_holder_task_id: int | None = None
_queue: list[int] = []
_POLL_SECONDS = 0.5

CancelCheck = Callable[[], bool] | Callable[[], Awaitable[bool]]


class BrowserControlCancelled(Exception):
    """Raised when a task is cancelled while waiting for the browser lock."""


def browser_agent_queue_status() -> dict[str, Any]:
    """Snapshot for Admin API / debugging."""
    return {
        "holder_task_id": _holder_task_id,
        "queue_task_ids": list(_queue),
        "queue_length": len(_queue),
        "locked": _lock.locked(),
    }


def is_browser_agent_busy() -> bool:
    return _lock.locked() or _holder_task_id is not None


def _enqueue(task_id: int) -> None:
    if task_id not in _queue:
        _queue.append(task_id)


def _dequeue(task_id: int) -> None:
    try:
        _queue.remove(task_id)
    except ValueError:
        pass


async def _cancelled(check: CancelCheck | None) -> bool:
    if check is None:
        return False
    result = check()
    if asyncio.iscoroutine(result):
        return bool(await result)
    return bool(result)


@asynccontextmanager
async def acquire_browser_control(
    task_id: int,
    *,
    is_cancelled: CancelCheck | None = None,
):
    """Wait until this task uniquely owns browser control, then release on exit.

    While waiting, ``task_id`` stays in the queue and the AgentTask should remain
    ``pending``. Cancel during wait raises ``BrowserControlCancelled`` without
    taking the lock. Returning from ``run_task`` (including ``waiting_user``)
    releases the lock so the next queued job can run.
    """
    global _holder_task_id

    _enqueue(task_id)
    acquired = False
    try:
        while True:
            if await _cancelled(is_cancelled):
                raise BrowserControlCancelled()
            try:
                await asyncio.wait_for(_lock.acquire(), timeout=_POLL_SECONDS)
                acquired = True
                break
            except asyncio.TimeoutError:
                continue

        if await _cancelled(is_cancelled):
            _lock.release()
            acquired = False
            raise BrowserControlCancelled()

        _dequeue(task_id)
        _holder_task_id = task_id
        try:
            yield
        finally:
            if _holder_task_id == task_id:
                _holder_task_id = None
            if acquired:
                _lock.release()
                acquired = False
    finally:
        _dequeue(task_id)
        if acquired:
            if _holder_task_id == task_id:
                _holder_task_id = None
            try:
                _lock.release()
            except RuntimeError:
                pass
