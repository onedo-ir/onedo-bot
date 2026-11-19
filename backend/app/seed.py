from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import AppSetting


def migrate_schema_to_single_user(engine: Engine) -> None:
    """حذف جدول کاربر و ستون‌های user_id از دیتابیس‌های قبلی."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())

    with engine.begin() as conn:
        for table in ("conversations", "agent_tasks", "credential_vault"):
            if table not in tables:
                continue
            fks = insp.get_foreign_keys(table)
            for fk in fks:
                referred = fk.get("referred_table")
                cols = fk.get("constrained_columns") or []
                if referred == "users" or "user_id" in cols:
                    name = fk.get("name")
                    if name:
                        conn.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{name}"'))

            cols = {c["name"] for c in insp.get_columns(table)}
            if "user_id" in cols:
                conn.execute(text(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS user_id'))

        if "users" in tables:
            conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))

        if "app_settings" in tables:
            conn.execute(
                text(
                    "DELETE FROM app_settings WHERE key IN "
                    "('ai_base_url', 'ai_model', 'ai_api_key')"
                )
            )


def seed_database(db: Session) -> None:
    defaults = {
        "browser_live_enabled": "true",
        "ask_on_uncertainty": "true",
    }
    for key, value in defaults.items():
        existing = db.query(AppSetting).filter(AppSetting.key == key).first()
        if not existing:
            db.add(AppSetting(key=key, value=value))
    db.commit()
