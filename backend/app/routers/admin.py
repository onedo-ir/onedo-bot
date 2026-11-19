from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
import yaml

from app.agent_service import cancel_agent_task
from app.browser_agent_lock import browser_agent_queue_status
from app.config import get_settings
from app.database import get_db
from app.models import AgentTask, Conversation, ScheduledTask, TaskStatus
from app.schedule_service import delete_scheduled_task, list_scheduled_tasks, read_steps_file
from app.schemas import (
    AgentConfigOut,
    BrowserAgentQueueOut,
    ScheduledTaskOut,
    StatsOut,
    TaskOut,
)
from app.security import verify_admin_api_token

settings = get_settings()

# External admin REST API (ADMIN_API_TOKEN) — بدون پنل وب مدیریت
api_router = APIRouter(
    prefix="/api/admin-api",
    tags=["admin-api"],
    dependencies=[Depends(verify_admin_api_token)],
)


def _stats(db: Session) -> StatsOut:
    return StatsOut(
        conversations_count=db.query(func.count(Conversation.id)).scalar() or 0,
        tasks_count=db.query(func.count(AgentTask.id)).scalar() or 0,
        running_tasks=db.query(func.count(AgentTask.id))
        .filter(AgentTask.status == TaskStatus.running)
        .scalar()
        or 0,
        completed_tasks=db.query(func.count(AgentTask.id))
        .filter(AgentTask.status == TaskStatus.completed)
        .scalar()
        or 0,
    )


def _list_tasks(db: Session) -> list[AgentTask]:
    return db.query(AgentTask).order_by(AgentTask.created_at.desc()).limit(200).all()


def _get_agent_config() -> AgentConfigOut:
    return AgentConfigOut(
        base_url=settings.openai_compatible_base_url,
        model=settings.openai_compatible_model,
        has_api_key=bool((settings.openai_compatible_api_key or "").strip()),
    )


def _cancel_task(db: Session, task_id: int) -> AgentTask:
    try:
        return cancel_agent_task(db, task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="کار یافت نشد") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="این کار قابل لغو نیست") from exc


def _scheduled_out(row: ScheduledTask) -> ScheduledTaskOut:
    text = read_steps_file(row.steps_file)
    return ScheduledTaskOut(
        id=row.id,
        title=row.title,
        interval_minutes=row.interval_minutes,
        steps_file=row.steps_file,
        enabled=row.enabled,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        last_task_id=row.last_task_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        steps_preview=(text[:2000] if text else ""),
    )


def _list_scheduled(db: Session) -> list[ScheduledTaskOut]:
    return [_scheduled_out(row) for row in list_scheduled_tasks(db)]


def _delete_scheduled(db: Session, schedule_id: int) -> dict:
    try:
        delete_scheduled_task(db, schedule_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="کار دوره‌ای یافت نشد") from exc
    return {"ok": True}


def _browser_agent_queue() -> BrowserAgentQueueOut:
    return BrowserAgentQueueOut(**browser_agent_queue_status())


@api_router.get("/stats", response_model=StatsOut)
def api_stats(db: Session = Depends(get_db)):
    return _stats(db)


@api_router.get("/browser-agent-queue", response_model=BrowserAgentQueueOut)
def api_browser_agent_queue():
    """Which agent holds the shared browser lock and who is waiting."""
    return _browser_agent_queue()


@api_router.get("/tasks", response_model=list[TaskOut])
def api_tasks(db: Session = Depends(get_db)):
    return _list_tasks(db)


@api_router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
def api_cancel_task(task_id: int, db: Session = Depends(get_db)):
    return _cancel_task(db, task_id)


@api_router.get("/agent-config", response_model=AgentConfigOut)
def api_agent_config():
    return _get_agent_config()


@api_router.get("/scheduled-tasks", response_model=list[ScheduledTaskOut])
def api_list_scheduled(db: Session = Depends(get_db)):
    return _list_scheduled(db)


@api_router.delete("/scheduled-tasks/{schedule_id}")
def api_delete_scheduled(schedule_id: int, db: Session = Depends(get_db)):
    return _delete_scheduled(db, schedule_id)


def build_openapi_document() -> dict:
    token = settings.admin_api_token
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Onedo bot Admin API",
            "version": "1.0.0",
            "description": (
                "REST API عملیاتی فقط‌خواندنی/آماری. "
                "توکن را با هدر X-Admin-Token یا Authorization: Bearer بفرستید. "
                "تنظیمات OpenAI فقط از متغیرهای محیطی خوانده می‌شوند."
            ),
        },
        "servers": [{"url": "/", "description": "همین سرویس"}],
        "components": {
            "securitySchemes": {
                "AdminTokenHeader": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Admin-Token",
                    "description": f"مقدار ADMIN_API_TOKEN (فعلی: {token})",
                },
                "AdminBearer": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "همان ADMIN_API_TOKEN",
                },
            }
        },
        "security": [{"AdminTokenHeader": []}, {"AdminBearer": []}],
        "paths": {
            "/api/admin-api/stats": {
                "get": {
                    "summary": "آمار کلی",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/admin-api/tasks": {
                "get": {
                    "summary": "فهرست کارهای ایجنت",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/admin-api/tasks/{task_id}/cancel": {
                "post": {
                    "summary": "لغو کار ایجنت (pending/running/waiting_user)",
                    "parameters": [
                        {
                            "name": "task_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "responses": {
                        "200": {"description": "OK"},
                        "400": {"description": "قابل لغو نیست"},
                        "404": {"description": "یافت نشد"},
                    },
                }
            },
            "/api/admin-api/agent-config": {
                "get": {
                    "summary": "تنظیمات مدل AI (فقط خواندنی از env)",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/admin-api/browser-agent-queue": {
                "get": {
                    "summary": (
                        "وضعیت صف کنترل مرورگر "
                        "(حداکثر یک ایجنت؛ کارهای دوره‌ای در صف می‌مانند)"
                    ),
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/admin-api/scheduled-tasks": {
                "get": {
                    "summary": "فهرست کارهای دوره‌ای ایجنت",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/admin-api/scheduled-tasks/{schedule_id}": {
                "delete": {
                    "summary": "حذف کار دوره‌ای و فایل مراحل",
                    "parameters": [
                        {
                            "name": "schedule_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "responses": {
                        "200": {"description": "OK"},
                        "404": {"description": "یافت نشد"},
                    },
                }
            },
            f"/api/{token}/docs/openapi.yml": {
                "get": {
                    "summary": "همین سند OpenAPI (بدون احراز هویت)",
                    "security": [],
                    "responses": {"200": {"description": "OpenAPI YAML/JSON"}},
                }
            },
        },
    }


docs_router = APIRouter(tags=["admin-docs"])


@docs_router.get("/api/{admin_token}/docs/openapi.yml")
def openapi_docs(admin_token: str, request: Request):
    if admin_token != settings.admin_api_token:
        raise HTTPException(status_code=404, detail="Not found")
    doc = build_openapi_document()
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return JSONResponse(doc)
    return PlainTextResponse(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
        media_type="application/yaml; charset=utf-8",
    )
