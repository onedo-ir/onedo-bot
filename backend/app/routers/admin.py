from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
import yaml

from app.config import get_settings
from app.database import get_db
from app.models import AgentTask, Conversation, TaskStatus
from app.schemas import AgentConfigOut, StatsOut, TaskOut
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


@api_router.get("/stats", response_model=StatsOut)
def api_stats(db: Session = Depends(get_db)):
    return _stats(db)


@api_router.get("/tasks", response_model=list[TaskOut])
def api_tasks(db: Session = Depends(get_db)):
    return _list_tasks(db)


@api_router.get("/agent-config", response_model=AgentConfigOut)
def api_agent_config():
    return _get_agent_config()


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
            "/api/admin-api/agent-config": {
                "get": {
                    "summary": "تنظیمات مدل AI (فقط خواندنی از env)",
                    "responses": {"200": {"description": "OK"}},
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
