from fastapi import APIRouter, Depends, HTTPException

from auth import (
    AdminIdentity,
    consume_ws_ticket,
    create_session,
    delete_session,
    get_current_admin,
    hash_pin,
    mint_ws_ticket,
    verify_pin,
)
from db import get_pool
from models import LoginRequest, LoginResponse, WsTicketResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Super admin only. Team admins never enter a PIN — see /login-link."""
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM admins WHERE team_id IS NULL LIMIT 1")
    if row is None or row["pin_hash"] is None or not verify_pin(body.pin, row["pin_hash"]):
        raise HTTPException(status_code=401, detail="PIN 錯誤")

    token = await create_session(row["id"])
    return LoginResponse(
        token=token, admin_id=row["id"], team_id=row["team_id"],
        display_name=row["display_name"], is_super=True,
    )


@router.post("/login-link/{admin_token}", response_model=LoginResponse)
async def login_by_link(admin_token: str):
    """Team admin access: the link itself is the credential — no PIN, no
    login form. Visiting /admin/link/{token} in the frontend calls this once
    to mint a normal session, then proceeds exactly like a PIN login would."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM admins WHERE admin_share_token = $1 AND team_id IS NOT NULL", admin_token
    )
    if row is None:
        raise HTTPException(status_code=404, detail="此連結無效或已被停用")

    token = await create_session(row["id"])
    return LoginResponse(
        token=token, admin_id=row["id"], team_id=row["team_id"],
        display_name=row["display_name"], is_super=False,
    )


@router.post("/logout")
async def logout(authorization: str = ""):
    if authorization.startswith("Bearer "):
        await delete_session(authorization.removeprefix("Bearer ").strip())
    return {"ok": True}


@router.post("/ws-ticket", response_model=WsTicketResponse)
async def admin_ws_ticket(admin: AdminIdentity = Depends(get_current_admin)):
    subject = f"admin:{admin.admin_id}"
    return WsTicketResponse(ticket=mint_ws_ticket(subject))
