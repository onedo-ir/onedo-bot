from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
import yaml

from app.config import get_settings
from app.database import get_db
from app.models import AgentTask, AppSetting, Conversation, TaskStatus, User, UserRole
from app.schemas import (
    AdminUserCreate,
    AgentConfigOut,
    AgentConfigUpdate,
    SettingOut,
    SettingUpdate,
    StatsOut,
    TaskOut,
    UserOut,
    UserUpdate,
)
from app.security import get_admin_user, hash_password, verify_admin_api_token

settings = get_settings()

# Panel admin (JWT role=admin)
panel_router = APIRouter(prefix="/api/admin", tags=["admin-panel"], dependencies=[Depends(get_admin_user)])

# External admin REST API (ADMIN_API_TOKEN)
api_router = APIRouter(
    prefix="/api/admin-api",
    tags=["admin-api"],
    dependencies=[Depends(verify_admin_api_token)],
)


def _stats(db: Session) -> StatsOut:
    return StatsOut(
        users_count=db.query(func.count(User.id)).scalar() or 0,
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


def _list_users(db: Session) -> list[User]:
    return db.query(User).order_by(User.id.asc()).all()


def _create_user(payload: AdminUserCreate, db: Session) -> User:
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=400, detail="ایمیل تکراری است")
    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name or payload.email.split("@")[0],
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _update_user(user_id: int, payload: UserUpdate, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.role is not None:
        user.role = payload.role
    if payload.theme_preference is not None:
        user.theme_preference = payload.theme_preference
    db.commit()
    db.refresh(user)
    return user


def _list_tasks(db: Session) -> list[AgentTask]:
    return db.query(AgentTask).order_by(AgentTask.created_at.desc()).limit(200).all()


def _get_agent_config(db: Session) -> AgentConfigOut:
    def val(key: str, default: str = "") -> str:
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        return row.value if row else default

    key = val("ai_api_key")
    return AgentConfigOut(
        base_url=val("ai_base_url", settings.openai_compatible_base_url),
        model=val("ai_model", settings.openai_compatible_model),
        has_api_key=bool(key),
    )


def _update_agent_config(payload: AgentConfigUpdate, db: Session) -> AgentConfigOut:
    mapping = {
        "base_url": "ai_base_url",
        "model": "ai_model",
        "api_key": "ai_api_key",
    }
    data = payload.model_dump(exclude_unset=True)
    for field, key in mapping.items():
        if field in data and data[field] is not None:
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            if not row:
                row = AppSetting(key=key, value=data[field])
                db.add(row)
            else:
                row.value = data[field]
    db.commit()
    return _get_agent_config(db)


def _list_settings(db: Session) -> list[AppSetting]:
    return db.query(AppSetting).order_by(AppSetting.key.asc()).all()


def _update_setting(key: str, payload: SettingUpdate, db: Session) -> AppSetting:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if not row:
        row = AppSetting(key=key, value=payload.value)
        db.add(row)
    else:
        row.value = payload.value
    db.commit()
    db.refresh(row)
    return row


@panel_router.get("/stats", response_model=StatsOut)
def panel_stats(db: Session = Depends(get_db)):
    return _stats(db)


@panel_router.get("/users", response_model=list[UserOut])
def panel_users(db: Session = Depends(get_db)):
    return _list_users(db)


@panel_router.post("/users", response_model=UserOut)
def panel_create_user(payload: AdminUserCreate, db: Session = Depends(get_db)):
    return _create_user(payload, db)


@panel_router.patch("/users/{user_id}", response_model=UserOut)
def panel_update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    return _update_user(user_id, payload, db)


@panel_router.get("/tasks", response_model=list[TaskOut])
def panel_tasks(db: Session = Depends(get_db)):
    return _list_tasks(db)


@panel_router.get("/agent-config", response_model=AgentConfigOut)
def panel_agent_config(db: Session = Depends(get_db)):
    return _get_agent_config(db)


@panel_router.put("/agent-config", response_model=AgentConfigOut)
def panel_update_agent_config(payload: AgentConfigUpdate, db: Session = Depends(get_db)):
    return _update_agent_config(payload, db)


@panel_router.get("/settings", response_model=list[SettingOut])
def panel_settings(db: Session = Depends(get_db)):
    return _list_settings(db)


@panel_router.put("/settings/{key}", response_model=SettingOut)
def panel_update_setting(key: str, payload: SettingUpdate, db: Session = Depends(get_db)):
    return _update_setting(key, payload, db)


@api_router.get("/stats", response_model=StatsOut)
def api_stats(db: Session = Depends(get_db)):
    return _stats(db)


@api_router.get("/users", response_model=list[UserOut])
def api_users(db: Session = Depends(get_db)):
    return _list_users(db)


@api_router.post("/users", response_model=UserOut)
def api_create_user(payload: AdminUserCreate, db: Session = Depends(get_db)):
    return _create_user(payload, db)


@api_router.patch("/users/{user_id}", response_model=UserOut)
def api_update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    return _update_user(user_id, payload, db)


@api_router.get("/tasks", response_model=list[TaskOut])
def api_tasks(db: Session = Depends(get_db)):
    return _list_tasks(db)


@api_router.get("/agent-config", response_model=AgentConfigOut)
def api_agent_config(db: Session = Depends(get_db)):
    return _get_agent_config(db)


@api_router.put("/agent-config", response_model=AgentConfigOut)
def api_update_agent_config(payload: AgentConfigUpdate, db: Session = Depends(get_db)):
    return _update_agent_config(payload, db)


@api_router.get("/settings", response_model=list[SettingOut])
def api_settings(db: Session = Depends(get_db)):
    return _list_settings(db)


@api_router.put("/settings/{key}", response_model=SettingOut)
def api_update_setting(key: str, payload: SettingUpdate, db: Session = Depends(get_db)):
    return _update_setting(key, payload, db)


def build_openapi_document() -> dict:
    token = settings.admin_api_token
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Onedo bot Admin API",
            "version": "1.0.0",
            "description": (
                "REST API برای اکشن‌های پنل ادمین. "
                "توکن را با هدر X-Admin-Token یا Authorization: Bearer بفرستید."
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
            "/api/admin-api/users": {
                "get": {
                    "summary": "فهرست کاربران",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "summary": "ساخت کاربر",
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/api/admin-api/users/{user_id}": {
                "patch": {
                    "summary": "ویرایش کاربر",
                    "parameters": [
                        {"name": "user_id", "in": "path", "required": True, "schema": {"type": "integer"}}
                    ],
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
                    "summary": "تنظیمات مدل AI",
                    "responses": {"200": {"description": "OK"}},
                },
                "put": {
                    "summary": "به‌روزرسانی مدل AI",
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/api/admin-api/settings": {
                "get": {
                    "summary": "تنظیمات برنامه",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/admin-api/settings/{key}": {
                "put": {
                    "summary": "به‌روزرسانی یک تنظیم",
                    "parameters": [
                        {"name": "key", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
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
