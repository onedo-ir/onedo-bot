import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.browser_client import BrowserClient
from app.security import PanelUser, get_current_user

router = APIRouter(tags=["browser"])


class NavigateBody(BaseModel):
    url: str


class PointBody(BaseModel):
    x: float
    y: float
    button: str = "left"


class TypeBody(BaseModel):
    text: str = ""


class PressBody(BaseModel):
    key: str = "Enter"


class ScrollBody(BaseModel):
    x: float | None = None
    y: float | None = None
    delta_x: float = 0
    delta_y: float = 0


@router.get("/api/browser/status")
async def browser_status(user: PanelUser = Depends(get_current_user)):
    client = BrowserClient()
    health = await client.health()
    current: dict[str, Any] = {}
    try:
        current = await client.current()
    except Exception:  # noqa: BLE001
        current = {}
    return {"health": health, "current": current, "user": user.email}


@router.post("/api/browser/reset")
async def browser_reset(_: PanelUser = Depends(get_current_user)):
    client = BrowserClient()
    return await client.reset()


@router.post("/api/browser/navigate")
async def browser_navigate(body: NavigateBody, _: PanelUser = Depends(get_current_user)):
    client = BrowserClient()
    return await client.navigate(body.url)


@router.post("/api/browser/input/click")
async def browser_input_click(body: PointBody, _: PanelUser = Depends(get_current_user)):
    client = BrowserClient()
    return await client.input_click(body.x, body.y, body.button)


@router.post("/api/browser/input/dblclick")
async def browser_input_dblclick(body: PointBody, _: PanelUser = Depends(get_current_user)):
    client = BrowserClient()
    return await client.input_dblclick(body.x, body.y)


@router.post("/api/browser/input/type")
async def browser_input_type(body: TypeBody, _: PanelUser = Depends(get_current_user)):
    client = BrowserClient()
    return await client.input_type(body.text)


@router.post("/api/browser/input/press")
async def browser_input_press(body: PressBody, _: PanelUser = Depends(get_current_user)):
    client = BrowserClient()
    return await client.press(body.key)


@router.post("/api/browser/input/scroll")
async def browser_input_scroll(body: ScrollBody, _: PanelUser = Depends(get_current_user)):
    client = BrowserClient()
    return await client.input_scroll(body.delta_x, body.delta_y, body.x, body.y)


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
                            "width": shot.get("width") or 1280,
                            "height": shot.get("height") or 800,
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
            await asyncio.sleep(0.8)
    except WebSocketDisconnect:
        return
