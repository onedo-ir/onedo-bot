import asyncio
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.browser_client import BrowserClient
from app.security import PanelUser, get_current_user

router = APIRouter(tags=["browser"])


@router.get("/api/browser/status")
async def browser_status(user: PanelUser = Depends(get_current_user)):
    client = BrowserClient()
    health = await client.health()
    current = {}
    try:
        current = await client.current()
    except Exception:  # noqa: BLE001
        current = {}
    return {"health": health, "current": current, "user": user.email}


@router.post("/api/browser/reset")
async def browser_reset(_: PanelUser = Depends(get_current_user)):
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
            except WebSocketDisconnect:
                return
            except Exception as exc:  # noqa: BLE001
                try:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": str(exc)})
                    )
                except Exception:  # noqa: BLE001
                    return
            await asyncio.sleep(1.2)
    except WebSocketDisconnect:
        return
