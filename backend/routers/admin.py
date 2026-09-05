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
    ChallengeAdminView,
    DevicePosition,
    ResolveChallengeResultBody,
    TeamPublic,
)
from routers.challenges import to_challenge_admin
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
            raise HTTPException(status_code=400, detail="需提供 success")
        return await resolve_challenge_result(request_id, admin.admin_id, body.success)
    raise HTTPException(status_code=400, detail="未知的請求類型")


@router.post("/deny/{request_id}", response_model=dict)
async def deny_request(team_id: int, request_id: int, admin: AdminIdentity = Depends(get_current_admin)):
    assert_team_scope(admin, team_id)
    kind = await _request_kind(request_id)
    if kind in ("claim", "topup"):
        return await resolve_action_request(request_id, admin.admin_id, approve=False)
    if kind == "challenge_start":
        return await resolve_challenge_start(request_id, admin.admin_id, approve=False)
    # challenge_result requests are auto-created once a start is approved and
    # are only ever resolved via /approve (判定成功/判定失敗) — there's no
    # "deny and let the team resubmit" path anymore, since the team never
    # submits a result themselves.
    raise HTTPException(status_code=400, detail="未知的請求類型")


@router.get("/challenges", response_model=list[ChallengeAdminView])
async def team_admin_challenges(team_id: int, admin: AdminIdentity = Depends(get_current_admin)):
    """Same active-pool challenge list a team sees on the map (GET
    /api/map/challenges), but for the judging admin — includes admin_notes
    (the answer key, if any) so a challenge_result approval can be checked
    without leaving this page. Content is global, same as /log;
    assert_team_scope only gates *access* to this admin surface."""
    assert_team_scope(admin, team_id)
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT c.*, (SELECT COUNT(*) FROM challenge_attempts
                         WHERE challenge_id = c.id AND status = 'failed') AS prior_fail_count
           FROM challenges c WHERE c.pool_state = 'active' ORDER BY c.id"""
    )
    return [to_challenge_admin(r) for r in rows]


@router.get("/gps", response_model=list[DevicePosition])
async def team_gps(team_id: int, admin: AdminIdentity = Depends(get_current_admin)):
    assert_team_scope(admin, team_id)
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM device_positions WHERE team_id = $1", team_id)
    return [DevicePosition(**dict(r)) for r in rows]


@router.get("/log", response_model=list[ActionLogEntry])
async def team_log(team_id: int, limit: int = Query(default=300, le=1000),
                    admin: AdminIdentity = Depends(get_current_admin)):
    # assert_team_scope still gates *access* to this admin surface; the log
    # content itself is global (every team's actions), same as the team view.
    assert_team_scope(admin, team_id)
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT al.*, t.name AS team_name FROM action_log al LEFT JOIN teams t ON t.id = al.team_id
           ORDER BY al.created_at DESC LIMIT $1""",
        limit,
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
            adjust_msg = f"管理員調整代幣：{body.reason}"
            await conn.execute("UPDATE teams SET chips_balance = $1 WHERE id = $2", new_balance, team_id)
            await conn.execute(
                """INSERT INTO action_log (team_id, actor, action_type, chip_delta, resulting_balance, message)
                   VALUES ($1, $2, 'admin_adjust', $3, $4, $5)""",
                team_id, admin.display_name, body.delta, new_balance, adjust_msg,
            )
    await manager.notify_team(team_id, "team_update")
    await manager.broadcast_global("ranking_update")
    await manager.broadcast_global(
        "activity_log", team_id=team_id, team_name=team["name"], action_type="admin_adjust",
        message=adjust_msg, chip_delta=body.delta,
    )
    return {"ok": True, "chips_balance": new_balance}
