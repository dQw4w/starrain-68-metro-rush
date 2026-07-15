import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException

from db import get_pool
from config import SESSION_TTL_HOURS, WS_TICKET_TTL_SECONDS

_PBKDF2_ITERATIONS = 200_000


def hash_pin(pin: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        salt, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest.hex(), digest_hex)


class AdminIdentity:
    def __init__(self, admin_id: int, team_id: Optional[int], display_name: str):
        self.admin_id = admin_id
        self.team_id = team_id  # None => super admin
        self.display_name = display_name

    @property
    def is_super(self) -> bool:
        return self.team_id is None


async def create_session(admin_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    pool = get_pool()
    await pool.execute(
        "INSERT INTO admin_sessions (token, admin_id, expires_at) VALUES ($1, $2, $3)",
        token, admin_id, expires_at,
    )
    return token


async def delete_session(token: str) -> None:
    pool = get_pool()
    await pool.execute("DELETE FROM admin_sessions WHERE token = $1", token)


async def resolve_session(token: str) -> Optional[AdminIdentity]:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT a.id, a.team_id, a.display_name
        FROM admin_sessions s
        JOIN admins a ON a.id = s.admin_id
        WHERE s.token = $1 AND s.expires_at > now()
        """,
        token,
    )
    if row is None:
        return None
    return AdminIdentity(row["id"], row["team_id"], row["display_name"])


async def get_current_admin(authorization: str = Header(default="")) -> AdminIdentity:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    identity = await resolve_session(token)
    if identity is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return identity


async def require_superadmin(admin: AdminIdentity = Depends(get_current_admin)) -> AdminIdentity:
    if not admin.is_super:
        raise HTTPException(status_code=403, detail="Super admin only")
    return admin


def assert_team_scope(admin: AdminIdentity, team_id: int) -> None:
    """Super admins may act on any team (backup approver); team admins only their own."""
    if not (admin.is_super or admin.team_id == team_id):
        raise HTTPException(status_code=403, detail="Not authorized for this team")


# --- Short-lived, single-use WebSocket auth tickets ---------------------------------
# Browsers can't set custom headers on the native WebSocket handshake, so we mint a
# one-time ticket via an authenticated REST call and pass that as a query param
# instead of the long-lived session token (which would otherwise land in access logs).
_ws_tickets: dict[str, tuple[str, float]] = {}  # ticket -> (subject, expires_at monotonic)


def mint_ws_ticket(subject: str) -> str:
    """subject encodes what the ticket authorizes, e.g. 'admin:<id>' or 'team:<token>'."""
    ticket = secrets.token_urlsafe(24)
    _ws_tickets[ticket] = (subject, time.monotonic() + WS_TICKET_TTL_SECONDS)
    return ticket


def consume_ws_ticket(ticket: str) -> Optional[str]:
    entry = _ws_tickets.pop(ticket, None)
    if entry is None:
        return None
    subject, expires_at = entry
    if time.monotonic() > expires_at:
        return None
    return subject
