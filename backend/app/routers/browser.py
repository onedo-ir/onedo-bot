import asyncio
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.browser_client import BrowserClient
from app.database import get_db
from app.models import User
from app.security import get_current_user

router = APIRouter(tags=["browser"])


@router.get("/api/browser/status")
async def browser_status(user: User = Depends(get_current_user)):
    client = BrowserClient()
    health = await client.health()
    current = {}
    try:
        current = await client.current()
    except Exception:  # noqa: BLE001
        current = {}
    return {"health": health, "current": current, "user": user.email}


@router.post("/api/browser/reset")
async def browser_reset(user: User = Depends(get_current_user)):
    client = BrowserClient()
    return await client.reset()


@router.websocket("/ws/browser")
async def browser_live(websocket: WebSocket):
    await websocket.accept()
    client = BrowserClient()
    try:
        while True:
            try:
                shot = await client.screenshot()
                current = await client.current()
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "frame",
                            "image": shot.get("image"),
                            "url": current.get("url"),
                            "title": current.get("title"),
                        }
                    )
                )
            except Exception as exc:  # noqa: BLE001
                await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
            await asyncio.sleep(1.2)
    except WebSocketDisconnect:
        return
