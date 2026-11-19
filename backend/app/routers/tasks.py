from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent_service import cancel_agent_task, run_task
from app.database import SessionLocal, get_db
from app.models import AgentTask, Message, MessageRole, TaskStatus
from app.schemas import TaskOut, TaskReply
from app.security import PanelUser, get_current_user

router = APIRouter(prefix="/api", tags=["tasks"])


async def _run_task_background(task_id: int) -> None:
    db = SessionLocal()
    try:
        await run_task(db, task_id)
    finally:
        db.close()


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(_: PanelUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(AgentTask).order_by(AgentTask.created_at.desc()).limit(100).all()


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int, _: PanelUser = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="کار یافت نشد")
    return task


@router.post("/tasks/{task_id}/reply", response_model=TaskOut)
def reply_task(
    task_id: int,
    payload: TaskReply,
    background_tasks: BackgroundTasks,
    _: PanelUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="کار یافت نشد")
    if task.status != TaskStatus.waiting_user:
        raise HTTPException(status_code=400, detail="این کار منتظر پاسخ نیست")

    task.instruction = f"{task.instruction}\n\nپاسخ کاربر: {payload.answer.strip()}"
    task.status = TaskStatus.pending
    task.waiting_question = None
    db.add(
        Message(
            conversation_id=task.conversation_id,
            role=MessageRole.user,
            content=payload.answer.strip(),
        )
    )
    db.commit()
    db.refresh(task)
    background_tasks.add_task(_run_task_background, task.id)
    return task


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
def cancel_task(task_id: int, _: PanelUser = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return cancel_agent_task(db, task_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="کار یافت نشد") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="این کار قابل لغو نیست") from None
