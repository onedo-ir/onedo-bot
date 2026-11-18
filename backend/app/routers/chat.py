from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent_service import run_task
from app.database import SessionLocal, get_db
from app.models import AgentTask, Conversation, Message, MessageRole, TaskStatus, User
from app.schemas import ConversationCreate, ConversationDetail, ConversationOut, MessageCreate, MessageOut, TaskOut
from app.security import get_current_user

router = APIRouter(prefix="/api/chat", tags=["chat"])


async def _run_task_background(task_id: int) -> None:
    db = SessionLocal()
    try:
        await run_task(db, task_id)
    finally:
        db.close()


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


@router.post("/conversations", response_model=ConversationOut)
def create_conversation(
    payload: ConversationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = Conversation(user_id=user.id, title=payload.title or "گفتگوی جدید")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="گفتگو یافت نشد")
    return conv


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="گفتگو یافت نشد")
    db.delete(conv)
    db.commit()
    return {"ok": True}


@router.post("/conversations/{conversation_id}/messages", response_model=dict)
def send_message(
    conversation_id: int,
    payload: MessageCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="گفتگو یافت نشد")

    user_msg = Message(conversation_id=conv.id, role=MessageRole.user, content=payload.content.strip())
    db.add(user_msg)

    if conv.title == "گفتگوی جدید":
        conv.title = payload.content.strip()[:60]

    waiting = (
        db.query(AgentTask)
        .filter(
            AgentTask.conversation_id == conv.id,
            AgentTask.status == TaskStatus.waiting_user,
        )
        .order_by(AgentTask.id.desc())
        .first()
    )

    if waiting:
        waiting.instruction = f"{waiting.instruction}\n\nپاسخ کاربر: {payload.content.strip()}"
        waiting.status = TaskStatus.pending
        waiting.waiting_question = None
        assistant = Message(
            conversation_id=conv.id,
            role=MessageRole.assistant,
            content="باشه، با راهنمایی شما ادامه می‌دهم…",
        )
        db.add(assistant)
        db.commit()
        db.refresh(waiting)
        background_tasks.add_task(_run_task_background, waiting.id)
        return {"message": MessageOut.model_validate(user_msg), "task": TaskOut.model_validate(waiting)}

    task = AgentTask(
        conversation_id=conv.id,
        user_id=user.id,
        instruction=payload.content.strip(),
        status=TaskStatus.pending,
    )
    db.add(task)
    assistant = Message(
        conversation_id=conv.id,
        role=MessageRole.assistant,
        content="دستور را گرفتم. مرورگر کروم را آماده می‌کنم و کار را شروع می‌کنم…",
    )
    db.add(assistant)
    db.commit()
    db.refresh(task)
    background_tasks.add_task(_run_task_background, task.id)
    return {"message": MessageOut.model_validate(user_msg), "task": TaskOut.model_validate(task)}
