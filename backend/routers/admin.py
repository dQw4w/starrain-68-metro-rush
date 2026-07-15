import json

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from auth import AdminIdentity, assert_team_scope, get_current_admin
from db import get_pool
from game_logic import (
    get_ranking,
    resolve_action_request,
    resolve_challenge_result,
    resolve_challenge_start,
)
from models import (
    ActionLogEntry,
    AdjustChipsBody,
    ApprovalRequestOut,
    DevicePosition,
    ResolveChallengeResultBody,
    TeamPublic,
)
from ws import manager

router = APIRouter(prefix="/api/admin/team/{team_id}", tags=["admin"])


def _normalize_request(r) -> dict:
    d = dict(r)
    if isinstance(d["requested_value"], str):
        d["requested_value"] = json.loads(d["requested_value"])
    return d


@router.get("/info", response_model=TeamPublic)
async def team_info(team_id: int, admin: AdminIdentity = Depends(get_current_admin)):
    assert_team_scope(admin, team_id)
    ranking = await get_ranking()
    for r in ranking:
        if r["id"] == team_id:
            return TeamPublic(**r)
    raise HTTPException(status_code=404, detail="找不到此隊伍")


@router.get("/pending", response_model=list[ApprovalRequestOut])
async def list_pending(team_id: int, admin: AdminIdentity = Depends(get_current_admin)):
    assert_team_scope(admin, team_id)
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM approval_requests WHERE team_id = $1 AND status = 'pending' ORDER BY created_at",
        team_id,
    )
    return [ApprovalRequestOut(**_normalize_request(r)) for r in rows]


async def _request_kind(request_id: int) -> str:
    pool = get_pool()
    kind = await pool.fetchval("SELECT kind FROM approval_requests WHERE id = $1", request_id)
    if kind is None:
        raise HTTPException(status_code=404, detail="找不到此請求")
    return kind


@router.post("/approve/{request_id}", response_model=dict)
async def approve_request(
    team_id: int, request_id: int,
    body: ResolveChallengeResultBody | None = Body(default=None),
    admin: AdminIdentity = Depends(get_current_admin),
):
    assert_team_scope(admin, team_id)
    kind = await _request_kind(request_id)
    if kind in ("claim", "topup"):
        return await resolve_action_request(request_id, admin.admin_id, approve=True)
    if kind == "challenge_start":
        return await resolve_challenge_start(request_id, admin.admin_id, approve=True)
    if kind == "challenge_result":
        if body is None:
            raise HTTPException(status_code=400, detail="需提供 success / achieved_value")
        return await resolve_challenge_result(request_id, admin.admin_id, body.success, body.achieved_value)
    raise HTTPException(status_code=400, detail="未知的請求類型")


@router.post("/deny/{request_id}", response_model=dict)
async def deny_request(team_id: int, request_id: int, admin: AdminIdentity = Depends(get_current_admin)):
    assert_team_scope(admin, team_id)
    kind = await _request_kind(request_id)
    if kind in ("claim", "topup"):
        return await resolve_action_request(request_id, admin.admin_id, approve=False)
    if kind == "challenge_start":
        return await resolve_challenge_start(request_id, admin.admin_id, approve=False)
    if kind == "challenge_result":
        # "Deny" on a result submission just sends it back — team must resubmit. We
        # implement this as denying the request without touching the attempt, so a
        # fresh submit-result call can create a new pending request.
        pool = get_pool()
        await pool.execute(
            "UPDATE approval_requests SET status = 'denied', resolved_by = $1, resolved_at = now() WHERE id = $2",
            admin.admin_id, request_id,
        )
        await manager.notify_admin(team_id, "admin_pending")
        return {"status": "denied"}
    raise HTTPException(status_code=400, detail="未知的請求類型")


@router.get("/gps", response_model=list[DevicePosition])
async def team_gps(team_id: int, admin: AdminIdentity = Depends(get_current_admin)):
    assert_team_scope(admin, team_id)
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM device_positions WHERE team_id = $1", team_id)
    return [DevicePosition(**dict(r)) for r in rows]


@router.get("/log", response_model=list[ActionLogEntry])
async def team_log(team_id: int, limit: int = Query(default=300, le=1000),
                    admin: AdminIdentity = Depends(get_current_admin)):
    assert_team_scope(admin, team_id)
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM action_log WHERE team_id = $1 ORDER BY created_at DESC LIMIT $2", team_id, limit
    )
    return [ActionLogEntry(**dict(r)) for r in rows]


@router.post("/adjust-chips", response_model=dict)
async def adjust_chips(team_id: int, body: AdjustChipsBody, admin: AdminIdentity = Depends(get_current_admin)):
    assert_team_scope(admin, team_id)
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            team = await conn.fetchrow("SELECT * FROM teams WHERE id = $1 FOR UPDATE", team_id)
            if team is None:
                raise HTTPException(status_code=404, detail="找不到此隊伍")
            new_balance = team["chips_balance"] + body.delta
            await conn.execute("UPDATE teams SET chips_balance = $1 WHERE id = $2", new_balance, team_id)
            await conn.execute(
                """INSERT INTO action_log (team_id, actor, action_type, chip_delta, resulting_balance, message)
                   VALUES ($1, $2, 'admin_adjust', $3, $4, $5)""",
                team_id, admin.display_name, body.delta, new_balance, f"管理員調整代幣：{body.reason}",
            )
    await manager.notify_team(team_id, "team_update")
    await manager.broadcast_global("ranking_update")
    return {"ok": True, "chips_balance": new_balance}
