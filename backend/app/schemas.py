import re
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

from app.models import MessageRole, TaskStatus, UserRole

# اجازهٔ دامنه‌های نمونه مثل .local (EmailStr آن‌ها را رد می‌کند)
Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=255),
]
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str) -> str:
    if not _EMAIL_RE.match(value):
        raise ValueError("فرمت ایمیل نامعتبر است")
    return value


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: Email
    password: str = Field(min_length=6)
    full_name: str = ""

    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "email", _validate_email(self.email))


class UserLogin(BaseModel):
    email: Email
    password: str

    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "email", _validate_email(self.email))


class UserOut(BaseModel):
    id: int
    email: Email
    full_name: str
    role: UserRole
    is_active: bool
    theme_preference: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None
    theme_preference: str | None = None
    is_active: bool | None = None
    role: UserRole | None = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)


class MessageOut(BaseModel):
    id: int
    role: MessageRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationCreate(BaseModel):
    title: str = "گفتگوی جدید"


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


class TaskOut(BaseModel):
    id: int
    conversation_id: int
    instruction: str
    status: TaskStatus
    summary: str | None
    current_url: str | None
    waiting_question: str | None
    steps_log: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskReply(BaseModel):
    answer: str = Field(min_length=1)


class CredentialCreate(BaseModel):
    label: str
    site_url: str = ""
    username: str = ""
    secret_note: str = ""


class CredentialOut(BaseModel):
    id: int
    label: str
    site_url: str
    username: str
    secret_note: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SettingUpdate(BaseModel):
    value: str


class SettingOut(BaseModel):
    key: str
    value: str

    model_config = {"from_attributes": True}


class StatsOut(BaseModel):
    users_count: int
    conversations_count: int
    tasks_count: int
    running_tasks: int
    completed_tasks: int


class AgentConfigOut(BaseModel):
    base_url: str
    model: str
    has_api_key: bool


class AgentConfigUpdate(BaseModel):
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


class AdminUserCreate(BaseModel):
    email: Email
    password: str = Field(min_length=6)
    full_name: str = ""
    role: UserRole = UserRole.user

    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "email", _validate_email(self.email))


class HealthOut(BaseModel):
    status: str
    app: str


class BrowserAction(BaseModel):
    action: str
    payload: dict[str, Any] = {}
