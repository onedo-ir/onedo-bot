from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models import AppSetting


def migrate_schema_to_single_user(engine: Engine) -> None:
    """حذف جدول کاربر و ستون‌های user_id از دیتابیس‌های قبلی.

    introspection را قبل از هر ALTER انجام می‌دهد تا قفل جدول روی یک اتصال
    و inspect روی اتصال دیگر باعث deadlock نشود.
    """
    statements: list[str] = []

    with engine.connect() as conn:
        insp = inspect(conn)
        tables = set(insp.get_table_names())

        for table in ("conversations", "agent_tasks"):
            if table not in tables:
                continue
            for fk in insp.get_foreign_keys(table):
                referred = fk.get("referred_table")
                cols = fk.get("constrained_columns") or []
                if referred == "users" or "user_id" in cols:
                    name = fk.get("name")
                    if name:
                        statements.append(
                            f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{name}"'
                        )

            col_names = {c["name"] for c in insp.get_columns(table)}
            if "user_id" in col_names:
                statements.append(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS user_id')

        if "users" in tables:
            statements.append("DROP TABLE IF EXISTS users CASCADE")

        # Credentials moved to /data/browser/credentials.json — no panel/DB vault.
        if "credential_vault" in tables:
            statements.append('DROP TABLE IF EXISTS "credential_vault" CASCADE')

        if "app_settings" in tables:
            statements.append(
                "DELETE FROM app_settings WHERE key IN "
                "('ai_base_url', 'ai_model', 'ai_api_key')"
            )

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


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
