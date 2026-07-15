import secrets

from fastapi import APIRouter, Depends, HTTPException

from auth import AdminIdentity, hash_pin, require_superadmin
from db import get_pool
from models import (
    ActionLogEntry,
    GameConfig,
    GameConfigUpdate,
    GamePhase,
    TeamAdminView,
    TeamCreate,
    TeamUpdate,
)
from game_logic import get_phase, get_ranking
from ws import manager

router = APIRouter(prefix="/api/superadmin", tags=["superadmin"])


@router.get("/config", response_model=GameConfig)
async def read_config(_: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM game_config WHERE id = 1")
    return GameConfig(**dict(row))


@router.put("/config", response_model=GameConfig)
async def update_config(body: GameConfigUpdate, _: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    current = await pool.fetchrow("SELECT * FROM game_config WHERE id = 1")
    if current["locked"]:
        # Once the game has started, only the emergency override + lock fields remain editable.
        allowed = {"override_status", "locked"}
        changed = {k for k, v in body.model_dump(exclude_unset=True).items() if k not in allowed}
        if changed:
            raise HTTPException(status_code=400, detail=f"遊戲已開始，無法修改：{', '.join(changed)}")

    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return GameConfig(**dict(current))

    set_clause = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(fields))
    values = list(fields.values())
    row = await pool.fetchrow(
        f"UPDATE game_config SET {set_clause} WHERE id = 1 RETURNING *", *values
    )
    await manager.broadcast_global("config_update")
    return GameConfig(**dict(row))


@router.get("/phase", response_model=GamePhase)
async def read_phase():
    return GamePhase(**await get_phase())


@router.get("/teams", response_model=list[TeamAdminView])
async def list_teams(_: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT t.*, COALESCE(sc.cnt, 0) AS stations_owned
        FROM teams t
        LEFT JOIN (
            SELECT owner_team_id, COUNT(*) AS cnt FROM station_claims
            WHERE owner_team_id IS NOT NULL GROUP BY owner_team_id
        ) sc ON sc.owner_team_id = t.id
        ORDER BY t.id
        """
    )
    return [
        TeamAdminView(
            id=r["id"], name=r["name"], color_hex=r["color_hex"],
            meeting_station_id=r["meeting_station_id"], chips_balance=r["chips_balance"],
            active=r["active"], stations_owned=r["stations_owned"], rank=0, share_token=r["share_token"],
        )
        for r in rows
    ]


@router.post("/teams", response_model=TeamAdminView)
async def create_team(body: TeamCreate, admin: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    cfg = await pool.fetchrow("SELECT * FROM game_config WHERE id = 1")
    if cfg["locked"]:
        raise HTTPException(status_code=400, detail="遊戲已開始，無法新增隊伍")

    share_token = secrets.token_urlsafe(8)
    async with pool.acquire() as conn:
        async with conn.transaction():
            team = await conn.fetchrow(
                """INSERT INTO teams (name, color_hex, meeting_station_id, chips_balance, admin_pin_hash, share_token)
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
                body.name, body.color_hex, body.meeting_station_id, cfg["starting_chips"],
                hash_pin(body.admin_pin), share_token,
            )
            await conn.execute(
                "INSERT INTO admins (team_id, display_name, pin_hash) VALUES ($1, $2, $3)",
                team["id"], f"{body.name} 隨隊管理員", hash_pin(body.admin_pin),
            )
    await manager.broadcast_global("config_update")
    return TeamAdminView(
        id=team["id"], name=team["name"], color_hex=team["color_hex"],
        meeting_station_id=team["meeting_station_id"], chips_balance=team["chips_balance"],
        active=team["active"], stations_owned=0, rank=0, share_token=team["share_token"],
    )


@router.put("/teams/{team_id}", response_model=TeamAdminView)
async def update_team(team_id: int, body: TeamUpdate, admin: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    fields = body.model_dump(exclude_unset=True, exclude={"admin_pin"})
    async with pool.acquire() as conn:
        async with conn.transaction():
            if fields:
                set_clause = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(fields))
                values = list(fields.values())
                team = await conn.fetchrow(
                    f"UPDATE teams SET {set_clause} WHERE id = ${len(values) + 1} RETURNING *",
                    *values, team_id,
                )
            else:
                team = await conn.fetchrow("SELECT * FROM teams WHERE id = $1", team_id)
            if team is None:
                raise HTTPException(status_code=404, detail="找不到此隊伍")
            if body.admin_pin:
                await conn.execute(
                    "UPDATE admins SET pin_hash = $1 WHERE team_id = $2", hash_pin(body.admin_pin), team_id
                )
    await manager.broadcast_global("config_update")
    stations_owned = await pool.fetchval(
        "SELECT COUNT(*) FROM station_claims WHERE owner_team_id = $1", team_id
    )
    return TeamAdminView(
        id=team["id"], name=team["name"], color_hex=team["color_hex"],
        meeting_station_id=team["meeting_station_id"], chips_balance=team["chips_balance"],
        active=team["active"], stations_owned=stations_owned, rank=0, share_token=team["share_token"],
    )


@router.get("/overview")
async def overview(_: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    ranking = await get_ranking()
    pending_counts = await pool.fetch(
        "SELECT team_id, COUNT(*) AS cnt FROM approval_requests WHERE status = 'pending' GROUP BY team_id"
    )
    pending_map = {r["team_id"]: r["cnt"] for r in pending_counts}
    return {
        "ranking": [{**dict(r), "pending_count": pending_map.get(r["id"], 0)} for r in ranking],
    }


@router.get("/log", response_model=list[ActionLogEntry])
async def global_log(_: AdminIdentity = Depends(require_superadmin), limit: int = 500):
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM action_log ORDER BY created_at DESC LIMIT $1", limit)
    return [ActionLogEntry(**dict(r)) for r in rows]
