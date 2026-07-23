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


@router.get("/resolve-admin-link/{admin_token}")
async def resolve_admin_link_route(admin_token: str):
    """Maps a team admin's permanent link token to its numeric team_id, so the
    frontend can build /api/admin/team/{team_id}/... calls. The token itself
    already *is* the credential (see auth.resolve_admin_link) — this lookup
    doesn't grant anything beyond what holding the token already grants."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT team_id FROM admins WHERE admin_share_token = $1 AND team_id IS NOT NULL", admin_token
    )
    if row is None:
        raise HTTPException(status_code=404, detail="此連結無效或已被停用")
    return {"team_id": row["team_id"]}


@router.post("/logout")
async def logout(authorization: str = ""):
    if authorization.startswith("Bearer "):
        await delete_session(authorization.removeprefix("Bearer ").strip())
    return {"ok": True}


@router.post("/ws-ticket", response_model=WsTicketResponse)
async def admin_ws_ticket(admin: AdminIdentity = Depends(get_current_admin)):
    subject = f"admin:{admin.admin_id}"
    return WsTicketResponse(ticket=mint_ws_ticket(subject))
