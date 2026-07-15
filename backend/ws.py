"""In-memory WebSocket connection manager.

Single-process by design (this is a one-day live event served from a single
container, not a horizontally-scaled service). Messages are lightweight
"something changed, go refetch" signals rather than full state payloads —
this keeps the server simple and makes the client's reconnect story trivial
(a reconnect just re-triggers the same refetches a live message would have).
"""
import json
from typing import Any

from fastapi import WebSocket
from loguru import logger


class ConnectionManager:
    def __init__(self) -> None:
        self.team_sockets: dict[int, set[WebSocket]] = {}
        self.admin_sockets: dict[int, set[WebSocket]] = {}
        self.super_sockets: set[WebSocket] = set()

    async def connect_team(self, team_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.team_sockets.setdefault(team_id, set()).add(ws)

    async def connect_admin(self, team_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.admin_sockets.setdefault(team_id, set()).add(ws)

    async def connect_super(self, ws: WebSocket) -> None:
        await ws.accept()
        self.super_sockets.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        for group in self.team_sockets.values():
            group.discard(ws)
        for group in self.admin_sockets.values():
            group.discard(ws)
        self.super_sockets.discard(ws)

    async def _send_all(self, sockets: set[WebSocket], payload: dict[str, Any]) -> None:
        dead = []
        data = json.dumps(payload)
        for ws in sockets:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            sockets.discard(ws)

    async def notify_team(self, team_id: int, event_type: str, **extra: Any) -> None:
        """Personal channel: this team's own members + their admin + super admins."""
        payload = {"type": event_type, "team_id": team_id, **extra}
        await self._send_all(self.team_sockets.get(team_id, set()), payload)
        await self._send_all(self.admin_sockets.get(team_id, set()), payload)
        await self._send_all(self.super_sockets, payload)

    async def notify_admin(self, team_id: int, event_type: str, **extra: Any) -> None:
        """Approval-queue channel: this team's admin + super admins only."""
        payload = {"type": event_type, "team_id": team_id, **extra}
        await self._send_all(self.admin_sockets.get(team_id, set()), payload)
        await self._send_all(self.super_sockets, payload)

    async def broadcast_global(self, event_type: str, **extra: Any) -> None:
        """Everyone: map/ranking/challenge-pool/config changes visible to all teams."""
        payload = {"type": event_type, **extra}
        for group in self.team_sockets.values():
            await self._send_all(group, payload)
        for group in self.admin_sockets.values():
            await self._send_all(group, payload)
        await self._send_all(self.super_sockets, payload)


manager = ConnectionManager()
