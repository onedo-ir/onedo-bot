from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AgentTask,
    AppSetting,
    Conversation,
    CredentialVault,
    Message,
    MessageRole,
    TaskStatus,
    User,
    UserRole,
)
from app.security import hash_password, verify_password

settings = get_settings()


def _ensure_password(user: User, plain: str) -> None:
    if not verify_password(plain, user.hashed_password):
        user.hashed_password = hash_password(plain)


def seed_database(db: Session) -> None:
    admin = db.query(User).filter(User.email == settings.default_admin_email).first()
    if not admin:
        admin = User(
            email=settings.default_admin_email,
            full_name="مدیر Onedo",
            hashed_password=hash_password(settings.default_admin_password),
            role=UserRole.admin,
            theme_preference="dark",
        )
        db.add(admin)
        db.flush()
    else:
        _ensure_password(admin, settings.default_admin_password)
        if admin.role != UserRole.admin:
            admin.role = UserRole.admin

    demo = db.query(User).filter(User.email == "demo@onedo.local").first()
    if not demo:
        demo = User(
            email="demo@onedo.local",
            full_name="کاربر نمونه",
            hashed_password=hash_password("Demo123!"),
            role=UserRole.user,
            theme_preference="dark",
        )
        db.add(demo)
        db.flush()

        conv = Conversation(user_id=demo.id, title="نمونه: خرید آنلاین")
        db.add(conv)
        db.flush()

        db.add_all(
            [
                Message(
                    conversation_id=conv.id,
                    role=MessageRole.user,
                    content="برو به یک فروشگاه نمونه و برای من یک هدفون بی‌سیم جستجو کن.",
                ),
                Message(
                    conversation_id=conv.id,
                    role=MessageRole.assistant,
                    content=(
                        "باشه! مرورگر را باز کردم و جستجو را شروع می‌کنم. "
                        "نتیجه را به‌صورت خلاصه اینجا می‌فرستم."
                    ),
                ),
            ]
        )

        db.add(
            AgentTask(
                conversation_id=conv.id,
                user_id=demo.id,
                instruction="جستجوی هدفون بی‌سیم در فروشگاه نمونه",
                status=TaskStatus.completed,
                summary="سه مدل هدفون پیدا شد؛ ارزان‌ترین حدود ۱٫۲ میلیون تومان بود.",
                current_url="https://example.com/search?q=wireless+headphones",
                steps_log=(
                    '[{"step":1,"action":"navigate","detail":"باز کردن صفحه جستجو"},'
                    '{"step":2,"action":"type","detail":"ورود عبارت هدفون بی‌سیم"},'
                    '{"step":3,"action":"extract","detail":"جمع‌آوری ۳ نتیجه"}]'
                ),
            )
        )

        db.add(
            CredentialVault(
                user_id=demo.id,
                label="ایمیل شخصی (نمونه)",
                site_url="https://mail.example.com",
                username="demo@example.com",
                secret_note="رمز واقعی ذخیره نشده — فقط برچسب نمونه",
            )
        )
    else:
        _ensure_password(demo, "Demo123!")

    defaults = {
        "ai_base_url": settings.openai_compatible_base_url,
        "ai_model": settings.openai_compatible_model,
        "ai_api_key": settings.openai_compatible_api_key or "",
        "browser_live_enabled": "true",
        "ask_on_uncertainty": "true",
    }
    for key, value in defaults.items():
        existing = db.query(AppSetting).filter(AppSetting.key == key).first()
        if not existing:
            db.add(AppSetting(key=key, value=value))

    db.commit()
