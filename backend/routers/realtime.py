from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from auth import consume_ws_ticket
from db import get_pool
from ws import manager

router = APIRouter(tags=["realtime"])


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, ticket: str):
    subject = consume_ws_ticket(ticket)
    if subject is None:
        await websocket.close(code=4401)
        return

    pool = get_pool()
    kind, _, value = subject.partition(":")

    if kind == "admin":
        admin = await pool.fetchrow("SELECT * FROM admins WHERE id = $1", int(value))
        if admin is None:
            await websocket.close(code=4401)
            return
        if admin["team_id"] is None:
            await manager.connect_super(websocket)
        else:
            await manager.connect_admin(admin["team_id"], websocket)
    elif kind == "team":
        team = await pool.fetchrow("SELECT id FROM teams WHERE share_token = $1", value)
        if team is None:
            await websocket.close(code=4401)
            return
        await manager.connect_team(team["id"], websocket)
    else:
        await websocket.close(code=4401)
        return

    try:
        while True:
            # Clients don't need to send anything; we just keep the socket open
            # and use this recv() as the mechanism to detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
