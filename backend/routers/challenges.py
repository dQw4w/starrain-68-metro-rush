import json

from fastapi import APIRouter, Depends, HTTPException

from auth import AdminIdentity, require_superadmin
from db import get_pool
from models import Challenge, ChallengeCreate, ChallengeTeaser, ChallengeUpdate
from game_logic import activate_initial_pool
from ws import manager

router = APIRouter(tags=["challenges"])


def _to_challenge(row) -> Challenge:
    d = dict(row)
    if isinstance(d["reward_config"], str):
        d["reward_config"] = json.loads(d["reward_config"])
    return Challenge(**d)


@router.get("/api/map/challenges", response_model=list[ChallengeTeaser])
async def list_active_challenges():
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM challenges WHERE pool_state = 'active' ORDER BY id")
    return [ChallengeTeaser(**{k: v for k, v in _to_challenge(r).model_dump().items() if k != "description"}) for r in rows]


@router.get("/api/team/{token}/challenge/{challenge_id}", response_model=Challenge)
async def team_challenge_detail(token: str, challenge_id: int):
    """Full challenge detail including the task description — only once this
    team has an attempt that's been approved to start (or beyond)."""
    pool = get_pool()
    team = await pool.fetchrow("SELECT id FROM teams WHERE share_token = $1", token)
    if team is None:
        raise HTTPException(status_code=404, detail="找不到此隊伍連結")
    attempt = await pool.fetchrow(
        "SELECT status FROM challenge_attempts WHERE challenge_id = $1 AND team_id = $2",
        challenge_id, team["id"],
    )
    if attempt is None or attempt["status"] == "pending_start_approval":
        raise HTTPException(status_code=403, detail="尚未獲得管理員核准開始，無法查看任務內容")
    row = await pool.fetchrow("SELECT * FROM challenges WHERE id = $1", challenge_id)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到此任務")
    return _to_challenge(row)


@router.get("/api/superadmin/challenges", response_model=list[Challenge])
async def list_all_challenges(_: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM challenges ORDER BY id")
    return [_to_challenge(r) for r in rows]


@router.post("/api/superadmin/challenges", response_model=Challenge)
async def create_challenge(body: ChallengeCreate, _: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO challenges (name, description, type, reward_config, location_name, lat, lng, image_url, pool_state)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *""",
        body.name, body.description, body.type, json.dumps(body.reward_config), body.location_name,
        body.lat, body.lng, body.image_url, body.pool_state,
    )
    if body.pool_state == "active":
        await manager.broadcast_global("challenge_pool")
    return _to_challenge(row)


@router.put("/api/superadmin/challenges/{challenge_id}", response_model=Challenge)
async def update_challenge(challenge_id: int, body: ChallengeUpdate, _: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    fields = body.model_dump(exclude_unset=True)
    if "reward_config" in fields:
        fields["reward_config"] = json.dumps(fields["reward_config"])
    if not fields:
        row = await pool.fetchrow("SELECT * FROM challenges WHERE id = $1", challenge_id)
    else:
        set_clause = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(fields))
        values = list(fields.values())
        row = await pool.fetchrow(
            f"UPDATE challenges SET {set_clause} WHERE id = ${len(values) + 1} RETURNING *",
            *values, challenge_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="找不到此任務")
    await manager.broadcast_global("challenge_pool")
    return _to_challenge(row)


@router.post("/api/superadmin/challenges/activate-pool")
async def activate_pool(_: AdminIdentity = Depends(require_superadmin)):
    await activate_initial_pool()
    return {"ok": True}
