from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schedule_service import delete_scheduled_task, list_scheduled_tasks, read_steps_file
from app.schemas import ScheduledTaskOut
from app.security import PanelUser, get_current_user

router = APIRouter(prefix="/api/scheduled-tasks", tags=["scheduled-tasks"])


def _to_out(row, *, with_preview: bool = True) -> ScheduledTaskOut:
    preview = None
    if with_preview:
        text = read_steps_file(row.steps_file)
        preview = text[:2000] if text else ""
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
        steps_preview=preview,
    )


@router.get("", response_model=list[ScheduledTaskOut])
def list_schedules(
    _: PanelUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [_to_out(row) for row in list_scheduled_tasks(db)]


@router.get("/{schedule_id}", response_model=ScheduledTaskOut)
def get_schedule(
    schedule_id: int,
    _: PanelUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models import ScheduledTask

    row = db.query(ScheduledTask).filter(ScheduledTask.id == schedule_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="کار دوره‌ای یافت نشد")
    return _to_out(row)


@router.delete("/{schedule_id}")
def remove_schedule(
    schedule_id: int,
    _: PanelUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_scheduled_task(db, schedule_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="کار دوره‌ای یافت نشد") from None
    return {"ok": True}
