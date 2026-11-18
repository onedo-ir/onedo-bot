import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.browser_client import BrowserClient
from app.models import AgentTask, AppSetting, Message, MessageRole, TaskStatus


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def append_step(task: AgentTask, step: dict[str, Any]) -> None:
    try:
        steps = json.loads(task.steps_log or "[]")
    except json.JSONDecodeError:
        steps = []
    step["step"] = len(steps) + 1
    steps.append(step)
    task.steps_log = json.dumps(steps, ensure_ascii=False)


async def call_llm(db: Session, instruction: str, page_text: str) -> dict[str, Any]:
    api_key = get_setting(db, "ai_api_key")
    base_url = get_setting(db, "ai_base_url", "https://api.openai.com/v1").rstrip("/")
    model = get_setting(db, "ai_model", "gpt-4o-mini")

    if not api_key:
        return {
            "mode": "heuristic",
            "plan": [
                {"action": "navigate", "url": "https://www.google.com"},
                {"action": "type", "selector": "textarea[name=q], input[name=q]", "text": instruction[:120]},
                {"action": "extract", "selector": "body"},
                {"action": "ask", "question": "آیا ادامه بدهم یا نتیجه جستجو کافی است؟"},
            ],
            "summary": "کلید API تنظیم نشده؛ اجرای آزمایشی با جستجوی گوگل انجام شد.",
        }

    system = (
        "You are Onedo bot, a careful browser agent. "
        "Return STRICT JSON with keys plan (list of actions) and summary (string). "
        "Allowed actions: navigate{url}, click{selector}, type{selector,text}, "
        "extract{selector}, ask{question}, done{}. "
        "If unsure or login needed, use ask. Keep selectors simple. Respond in Persian summary."
    )
    user_prompt = (
        f"Instruction:\n{instruction}\n\n"
        f"Current page text (truncated):\n{page_text[:4000]}\n"
    )

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        data["mode"] = "llm"
        return data


async def run_task(db: Session, task_id: int) -> AgentTask:
    task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not task:
        raise ValueError("task not found")

    task.status = TaskStatus.running
    task.waiting_question = None
    db.commit()

    browser = BrowserClient()
    try:
        current = await browser.current()
        page_text = (await browser.extract("body")).get("text", "")
        plan_data = await call_llm(db, task.instruction, page_text)
        plan = plan_data.get("plan") or []

        for item in plan:
            action = (item.get("action") or "").lower()
            if action == "navigate":
                result = await browser.navigate(item.get("url", "https://example.com"))
                task.current_url = result.get("url")
                append_step(task, {"action": "navigate", "detail": task.current_url})
            elif action == "click":
                result = await browser.click(item.get("selector", "body"))
                task.current_url = result.get("url", task.current_url)
                append_step(task, {"action": "click", "detail": item.get("selector")})
            elif action == "type":
                result = await browser.type_text(
                    item.get("selector", "input"), item.get("text", "")
                )
                task.current_url = result.get("url", task.current_url)
                append_step(task, {"action": "type", "detail": item.get("text", "")[:80]})
            elif action == "extract":
                result = await browser.extract(item.get("selector", "body"))
                append_step(task, {"action": "extract", "detail": (result.get("text") or "")[:120]})
            elif action == "ask":
                task.status = TaskStatus.waiting_user
                task.waiting_question = item.get("question") or "برای ادامه راهنمایی کنید."
                append_step(task, {"action": "ask", "detail": task.waiting_question})
                db.add(
                    Message(
                        conversation_id=task.conversation_id,
                        role=MessageRole.assistant,
                        content=f"⏸ کار متوقف شد.\n{task.waiting_question}",
                    )
                )
                db.commit()
                db.refresh(task)
                return task
            elif action == "done":
                break

        extract = await browser.extract("body")
        task.current_url = (await browser.current()).get("url", task.current_url)
        task.summary = plan_data.get("summary") or (extract.get("text") or "")[:500]
        task.status = TaskStatus.completed
        append_step(task, {"action": "done", "detail": "کار تمام شد"})
        db.add(
            Message(
                conversation_id=task.conversation_id,
                role=MessageRole.assistant,
                content=f"✅ خلاصه نتیجه:\n{task.summary}",
            )
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        task.status = TaskStatus.waiting_user
        task.waiting_question = (
            f"خطا رخ داد: {exc}. چطور ادامه بدهم؟ می‌توانید راهنمایی کنید یا کار را لغو کنید."
        )
        append_step(task, {"action": "error", "detail": str(exc)})
        db.add(
            Message(
                conversation_id=task.conversation_id,
                role=MessageRole.assistant,
                content=f"⚠ {task.waiting_question}",
            )
        )
        db.commit()

    db.refresh(task)
    return task
