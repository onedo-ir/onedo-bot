import re
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

from app.models import MessageRole, TaskStatus

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


class UserLogin(BaseModel):
    email: Email
    password: str

    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "email", _validate_email(self.email))


class PanelUserOut(BaseModel):
    email: Email
    full_name: str
    theme_preference: str = "dark"


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


class StatsOut(BaseModel):
    conversations_count: int
    tasks_count: int
    running_tasks: int
    completed_tasks: int


class AgentConfigOut(BaseModel):
    base_url: str
    model: str
    has_api_key: bool


class HealthOut(BaseModel):
    status: str
    app: str


class BrowserAction(BaseModel):
    action: str
    payload: dict[str, Any] = {}
