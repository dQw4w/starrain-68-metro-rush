import json

from fastapi import APIRouter, HTTPException, Query

from auth import mint_ws_ticket
from db import get_pool
from game_logic import (
    create_action_request,
    create_challenge_result_request,
    create_challenge_start_request,
    get_pending_for_team,
    get_phase,
    get_ranking,
)
from models import (
    ActionLogEntry,
    ApprovalRequestOut,
    ChallengeStartRequest,
    ChallengeSubmitResultRequest,
    ClaimRequestCreate,
    DevicePosition,
    GamePhase,
    GpsPing,
    TeamPublic,
    TeamSelf,
    TeamState,
    WsTicketResponse,
)
from ws import manager

router = APIRouter(prefix="/api/team/{token}", tags=["team"])


async def _team_by_token(token: str):
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM teams WHERE share_token = $1", token)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到此隊伍連結")
    return row


def _normalize_request(r) -> dict:
    d = dict(r)
    if isinstance(d["requested_value"], str):
        d["requested_value"] = json.loads(d["requested_value"])
    return d


@router.get("/state", response_model=TeamState)
async def team_state(token: str):
    team = await _team_by_token(token)
    phase = await get_phase()
    ranking = await get_ranking()
    pending = await get_pending_for_team(team["id"])
    return TeamState(
        team=TeamSelf(
            id=team["id"], name=team["name"], color_hex=team["color_hex"],
            meeting_station_id=team["meeting_station_id"], chips_balance=team["chips_balance"],
            share_token=team["share_token"],
        ),
        phase=GamePhase(**phase),
        ranking=[
            TeamPublic(
                id=r["id"], name=r["name"], color_hex=r["color_hex"], meeting_station_id=r["meeting_station_id"],
                chips_balance=r["chips_balance"], active=r["active"], stations_owned=r["stations_owned"], rank=r["rank"],
            )
            for r in ranking
        ],
        pending_requests=[ApprovalRequestOut(**_normalize_request(r)) for r in pending],
    )


@router.get("/log", response_model=list[ActionLogEntry])
async def team_log(token: str, action_type: str | None = Query(default=None), limit: int = Query(default=200, le=500)):
    team = await _team_by_token(token)
    pool = get_pool()
    if action_type:
        rows = await pool.fetch(
            "SELECT * FROM action_log WHERE team_id = $1 AND action_type = $2 ORDER BY created_at DESC LIMIT $3",
            team["id"], action_type, limit,
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM action_log WHERE team_id = $1 ORDER BY created_at DESC LIMIT $2",
            team["id"], limit,
        )
    return [ActionLogEntry(**dict(r)) for r in rows]


@router.post("/action", response_model=dict)
async def team_action(token: str, body: ClaimRequestCreate):
    team = await _team_by_token(token)
    return await create_action_request(team["id"], body.station_id, body.kind, body.requested_by, body.amount)


@router.post("/challenge/{challenge_id}/start", response_model=dict)
async def challenge_start(token: str, challenge_id: int, body: ChallengeStartRequest):
    team = await _team_by_token(token)
    return await create_challenge_start_request(
        team["id"], challenge_id, body.called_shot_value, body.target_team_id, body.requested_by
    )


@router.post("/challenge/{challenge_id}/submit-result", response_model=dict)
async def challenge_submit_result(token: str, challenge_id: int, body: ChallengeSubmitResultRequest):
    team = await _team_by_token(token)
    return await create_challenge_result_request(team["id"], challenge_id, body.achieved_value)


@router.get("/my-attempts")
async def my_attempts(token: str):
    team = await _team_by_token(token)
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM challenge_attempts WHERE team_id = $1", team["id"])
    return [dict(r) for r in rows]


@router.post("/gps")
async def gps_ping(token: str, body: GpsPing):
    team = await _team_by_token(token)
    pool = get_pool()
    await pool.execute(
        """INSERT INTO device_positions (team_id, device_id, lat, lng, updated_at)
           VALUES ($1, $2, $3, $4, now())
           ON CONFLICT (team_id, device_id) DO UPDATE SET lat = $3, lng = $4, updated_at = now()""",
        team["id"], body.device_id, body.lat, body.lng,
    )
    await manager.notify_team(team["id"], "gps_update")
    return {"ok": True}


@router.get("/gps", response_model=list[DevicePosition])
async def gps_list(token: str):
    team = await _team_by_token(token)
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM device_positions WHERE team_id = $1", team["id"])
    return [DevicePosition(**dict(r)) for r in rows]


@router.post("/ws-ticket", response_model=WsTicketResponse)
async def team_ws_ticket(token: str):
    await _team_by_token(token)
    return WsTicketResponse(ticket=mint_ws_ticket(f"team:{token}"))
