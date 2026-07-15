"""Transactional game-rule logic: schedule phase, station claim/topup/toll,
challenge attempt lifecycle, ranking. Routers stay thin and call into here.

Every chip-mutating action runs inside one asyncpg transaction with explicit
row locks (SELECT ... FOR UPDATE) so concurrent requests can't race each
other into an inconsistent state. WebSocket broadcasts are always fired
*after* the transaction block has exited (i.e. after commit), never from
inside it.
"""
import json
import math
import random
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException

from db import get_pool
from ws import manager

TAIPEI_TZ = timezone(timedelta(hours=8))


def _combine(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=TAIPEI_TZ)


async def get_phase() -> dict:
    pool = get_pool()
    cfg = await pool.fetchrow("SELECT * FROM game_config WHERE id = 1")
    now = datetime.now(TAIPEI_TZ)
    start_at = _combine(cfg["game_date"], cfg["start_time"])
    end_at = _combine(cfg["game_date"], cfg["end_time"])
    lunch_start_at = _combine(cfg["game_date"], cfg["lunch_start"])
    lunch_end_at = _combine(cfg["game_date"], cfg["lunch_end"])

    if cfg["override_status"] == "paused":
        phase = "paused"
    elif cfg["override_status"] == "force_ended":
        phase = "ended"
    elif now < start_at:
        phase = "not_started"
    elif now >= end_at:
        phase = "ended"
    elif lunch_start_at <= now < lunch_end_at:
        phase = "lunch_break"
    else:
        phase = "active"

    return {
        "phase": phase,
        "server_time": now,
        "game_date": cfg["game_date"],
        "start_at": start_at,
        "end_at": end_at,
        "lunch_start_at": lunch_start_at,
        "lunch_end_at": lunch_end_at,
    }


async def assert_active_phase() -> None:
    phase = await get_phase()
    if phase["phase"] != "active":
        messages = {
            "not_started": "遊戲尚未開始",
            "lunch_break": "目前為午休時間，暫停所有遊戲操作",
            "ended": "遊戲已結束",
            "paused": "遊戲已被管理員暫停",
        }
        raise HTTPException(status_code=403, detail=messages.get(phase["phase"], "目前無法進行操作"))


async def _log(conn, team_id, actor, action_type, *, station_id=None, challenge_id=None,
                chip_delta=None, resulting_balance=None, message):
    await conn.execute(
        """INSERT INTO action_log
               (team_id, actor, action_type, station_id, challenge_id, chip_delta, resulting_balance, message)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
        team_id, actor, action_type, station_id, challenge_id, chip_delta, resulting_balance, message,
    )


_EVENT_DISPATCH = {
    "notify_team": lambda team_id, event: manager.notify_team(team_id, event),
    "notify_admin": lambda team_id, event: manager.notify_admin(team_id, event),
}


async def _fire(events: list[tuple]) -> None:
    for ev in events:
        kind = ev[0]
        if kind == "broadcast_global":
            await manager.broadcast_global(ev[1])
        else:
            team_id, event = ev[1], ev[2]
            await _EVENT_DISPATCH[kind](team_id, event)


# ---------------------------------------------------------------------------
# Station claim / top-up / toll
# ---------------------------------------------------------------------------

async def create_action_request(team_id: int, station_id: int, kind: str,
                                  requested_by: str | None, amount: int | None = None) -> dict:
    await assert_active_phase()
    pool = get_pool()
    result: dict = {}
    events: list[tuple] = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                """SELECT * FROM approval_requests
                   WHERE team_id = $1 AND station_id = $2 AND kind = ANY($3::text[]) AND status = 'pending'""",
                team_id, station_id, ["claim", "topup"],
            )
            if existing is not None:
                result = {"status": "pending", "request": dict(existing)}
            else:
                claim = await conn.fetchrow("SELECT * FROM station_claims WHERE station_id = $1 FOR UPDATE", station_id)
                team = await conn.fetchrow("SELECT * FROM teams WHERE id = $1 FOR UPDATE", team_id)
                cfg = await conn.fetchrow("SELECT * FROM game_config WHERE id = 1")
                if claim is None or team is None:
                    raise HTTPException(status_code=404, detail="車站或隊伍不存在")

                if kind == "topup" and claim["owner_team_id"] != team_id:
                    raise HTTPException(status_code=400, detail="只能對己方車站加碼")
                if kind == "claim" and claim["owner_team_id"] == team_id:
                    raise HTTPException(status_code=400, detail="此車站已為己方所有，請使用加碼")
                if claim["value"] >= cfg["max_deposit_per_visit"]:
                    raise HTTPException(status_code=400, detail="此車站代幣數已達上限，無法再變動")

                if kind == "claim" and claim["owner_team_id"] is not None and team["chips_balance"] < 0:
                    # Negative-balance team passing through enemy territory: deterministic
                    # toll, executed immediately with no admin judgment call needed.
                    cost = claim["value"] + 1
                    owner_id = claim["owner_team_id"]
                    await conn.execute("UPDATE teams SET chips_balance = chips_balance - $1 WHERE id = $2", cost, team_id)
                    await conn.execute("UPDATE teams SET chips_balance = chips_balance + $1 WHERE id = $2", cost, owner_id)
                    payer_balance = team["chips_balance"] - cost
                    owner_row = await conn.fetchrow("SELECT chips_balance FROM teams WHERE id = $1", owner_id)
                    await _log(conn, team_id, "team", "toll_paid", station_id=station_id,
                               chip_delta=-cost, resulting_balance=payer_balance,
                               message=f"通行費：經過對方車站，支付 {cost} 枚代幣")
                    await _log(conn, owner_id, "team", "toll_received", station_id=station_id,
                               chip_delta=cost, resulting_balance=owner_row["chips_balance"],
                               message=f"收到通行費 {cost} 枚代幣")
                    result = {"status": "toll", "cost": cost}
                    events = [
                        ("notify_team", team_id, "team_update"),
                        ("notify_team", owner_id, "team_update"),
                        ("broadcast_global", "ranking_update"),
                    ]
                else:
                    req = await conn.fetchrow(
                        """INSERT INTO approval_requests (kind, team_id, station_id, requested_by, requested_value, status)
                           VALUES ($1, $2, $3, $4, $5, 'pending') RETURNING *""",
                        kind, team_id, station_id, requested_by,
                        json.dumps({"station_value": claim["value"], "owner_team_id": claim["owner_team_id"]}),
                    )
                    result = {"status": "pending", "request": dict(req)}
                    events = [("notify_admin", team_id, "admin_pending")]

    await _fire(events)
    return result


async def resolve_action_request(request_id: int, admin_id: int, approve: bool) -> dict:
    pool = get_pool()
    result: dict = {}
    events: list[tuple] = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            req = await conn.fetchrow("SELECT * FROM approval_requests WHERE id = $1 FOR UPDATE", request_id)
            if req is None:
                raise HTTPException(status_code=404, detail="找不到此請求")
            if req["kind"] not in ("claim", "topup"):
                raise HTTPException(status_code=400, detail="請求類型錯誤")
            if req["status"] != "pending":
                raise HTTPException(status_code=409, detail="此請求已被處理過")

            if not approve:
                await conn.execute(
                    "UPDATE approval_requests SET status = 'denied', resolved_by = $1, resolved_at = now() WHERE id = $2",
                    admin_id, request_id,
                )
                result = {"status": "denied"}
                events = [("notify_team", req["team_id"], "team_update"), ("notify_admin", req["team_id"], "admin_pending")]
            else:
                claim = await conn.fetchrow("SELECT * FROM station_claims WHERE station_id = $1 FOR UPDATE", req["station_id"])
                cfg = await conn.fetchrow("SELECT * FROM game_config WHERE id = 1")

                stale = (
                    (req["kind"] == "topup" and claim["owner_team_id"] != req["team_id"])
                    or (req["kind"] == "claim" and claim["owner_team_id"] == req["team_id"])
                    or claim["value"] >= cfg["max_deposit_per_visit"]
                )
                if stale:
                    await conn.execute(
                        "UPDATE approval_requests SET status = 'stale', resolved_by = $1, resolved_at = now() WHERE id = $2",
                        admin_id, request_id,
                    )
                    result = {"status": "stale"}
                    events = [("notify_admin", req["team_id"], "admin_pending")]
                else:
                    deposit = claim["value"] + 1  # authoritative recompute — never trust the tap-time snapshot
                    new_owner = req["team_id"]
                    prev_owner = claim["owner_team_id"]

                    team = await conn.fetchrow("SELECT chips_balance FROM teams WHERE id = $1 FOR UPDATE", new_owner)
                    await conn.execute("UPDATE teams SET chips_balance = chips_balance - $1 WHERE id = $2", deposit, new_owner)
                    await conn.execute(
                        "UPDATE station_claims SET owner_team_id = $1, value = $2, updated_at = now() WHERE station_id = $3",
                        new_owner, deposit, req["station_id"],
                    )
                    new_balance = team["chips_balance"] - deposit
                    action_label = "佔領" if req["kind"] == "claim" else "加碼"
                    await _log(conn, new_owner, "team", req["kind"], station_id=req["station_id"],
                               chip_delta=-deposit, resulting_balance=new_balance,
                               message=f"{action_label}車站，投入 {deposit} 枚代幣")
                    await conn.execute(
                        "UPDATE approval_requests SET status = 'approved', resolved_by = $1, resolved_at = now() WHERE id = $2",
                        admin_id, request_id,
                    )
                    result = {"status": "approved", "deposit": deposit}
                    events = [
                        ("notify_team", new_owner, "team_update"),
                        ("notify_admin", new_owner, "admin_pending"),
                        ("broadcast_global", "map_update"),
                        ("broadcast_global", "ranking_update"),
                    ]
                    if prev_owner and prev_owner != new_owner:
                        events.append(("notify_team", prev_owner, "team_update"))

    await _fire(events)
    return result


# ---------------------------------------------------------------------------
# Challenges
# ---------------------------------------------------------------------------

async def create_challenge_start_request(team_id: int, challenge_id: int, called_shot_value: int | None,
                                           target_team_id: int | None, requested_by: str | None) -> dict:
    await assert_active_phase()
    pool = get_pool()
    result: dict = {}
    events: list[tuple] = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            existing_req = await conn.fetchrow(
                """SELECT * FROM approval_requests
                   WHERE team_id = $1 AND challenge_id = $2 AND kind = 'challenge_start' AND status = 'pending'""",
                team_id, challenge_id,
            )
            if existing_req is not None:
                result = {"status": "pending", "request": dict(existing_req)}
            else:
                challenge = await conn.fetchrow("SELECT * FROM challenges WHERE id = $1 FOR UPDATE", challenge_id)
                if challenge is None:
                    raise HTTPException(status_code=404, detail="找不到此任務")
                if challenge["pool_state"] != "active":
                    raise HTTPException(status_code=400, detail="此任務目前不在地圖上")
                already = await conn.fetchrow(
                    "SELECT id FROM challenge_attempts WHERE challenge_id = $1 AND team_id = $2", challenge_id, team_id
                )
                if already is not None:
                    raise HTTPException(status_code=400, detail="此任務貴隊已經嘗試過了")
                if challenge["type"] == "steal" and target_team_id is None:
                    raise HTTPException(status_code=400, detail="偷竊任務需指定目標隊伍")

                req = await conn.fetchrow(
                    """INSERT INTO approval_requests (kind, team_id, challenge_id, requested_by, requested_value, status)
                       VALUES ('challenge_start', $1, $2, $3, $4, 'pending') RETURNING *""",
                    team_id, challenge_id, requested_by,
                    json.dumps({"called_shot_value": called_shot_value, "target_team_id": target_team_id}),
                )
                result = {"status": "pending", "request": dict(req)}
                events = [("notify_admin", team_id, "admin_pending")]

    await _fire(events)
    return result


async def resolve_challenge_start(request_id: int, admin_id: int, approve: bool) -> dict:
    pool = get_pool()
    result: dict = {}
    events: list[tuple] = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            req = await conn.fetchrow("SELECT * FROM approval_requests WHERE id = $1 FOR UPDATE", request_id)
            if req is None:
                raise HTTPException(status_code=404, detail="找不到此請求")
            if req["kind"] != "challenge_start":
                raise HTTPException(status_code=400, detail="請求類型錯誤")
            if req["status"] != "pending":
                raise HTTPException(status_code=409, detail="此請求已被處理過")

            if not approve:
                await conn.execute(
                    "UPDATE approval_requests SET status = 'denied', resolved_by = $1, resolved_at = now() WHERE id = $2",
                    admin_id, request_id,
                )
                result = {"status": "denied"}
                events = [("notify_team", req["team_id"], "team_update"), ("notify_admin", req["team_id"], "admin_pending")]
            else:
                challenge = await conn.fetchrow("SELECT * FROM challenges WHERE id = $1 FOR UPDATE", req["challenge_id"])
                cfg = await conn.fetchrow("SELECT * FROM game_config WHERE id = 1")
                already = await conn.fetchrow(
                    "SELECT id FROM challenge_attempts WHERE challenge_id = $1 AND team_id = $2",
                    req["challenge_id"], req["team_id"],
                )
                if challenge["pool_state"] != "active" or already is not None:
                    await conn.execute(
                        "UPDATE approval_requests SET status = 'stale', resolved_by = $1, resolved_at = now() WHERE id = $2",
                        admin_id, request_id,
                    )
                    result = {"status": "stale"}
                    events = [("notify_admin", req["team_id"], "admin_pending")]
                else:
                    prior_fails = await conn.fetchval(
                        "SELECT COUNT(*) FROM challenge_attempts WHERE challenge_id = $1 AND status = 'failed'",
                        req["challenge_id"],
                    )
                    fail_bonus_pct = float(prior_fails) * float(cfg["fail_bonus_step_pct"])
                    rv = req["requested_value"]
                    if isinstance(rv, str):
                        rv = json.loads(rv)
                    called_shot_value = rv.get("called_shot_value")
                    target_team_id = rv.get("target_team_id")

                    attempt = await conn.fetchrow(
                        """INSERT INTO challenge_attempts
                               (challenge_id, team_id, status, called_shot_value, target_team_id,
                                fail_bonus_pct_locked, started_at)
                           VALUES ($1, $2, 'in_progress', $3, $4, $5, now()) RETURNING *""",
                        req["challenge_id"], req["team_id"], called_shot_value, target_team_id, fail_bonus_pct,
                    )
                    await conn.execute(
                        """UPDATE approval_requests
                           SET status = 'approved', resolved_by = $1, resolved_at = now(), challenge_attempt_id = $2
                           WHERE id = $3""",
                        admin_id, attempt["id"], request_id,
                    )
                    await _log(conn, req["team_id"], "admin", "challenge_start_approved",
                               challenge_id=req["challenge_id"], message=f"任務「{challenge['name']}」開始")
                    result = {"status": "approved", "attempt_id": attempt["id"]}
                    events = [("notify_team", req["team_id"], "team_update"), ("notify_admin", req["team_id"], "admin_pending")]

    await _fire(events)
    return result


async def create_challenge_result_request(team_id: int, challenge_id: int, achieved_value: int | None) -> dict:
    await assert_active_phase()
    pool = get_pool()
    result: dict = {}
    events: list[tuple] = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            attempt = await conn.fetchrow(
                "SELECT * FROM challenge_attempts WHERE challenge_id = $1 AND team_id = $2 FOR UPDATE",
                challenge_id, team_id,
            )
            if attempt is None or attempt["status"] != "in_progress":
                raise HTTPException(status_code=400, detail="此任務目前不是進行中狀態")

            existing_req = await conn.fetchrow(
                """SELECT * FROM approval_requests
                   WHERE challenge_attempt_id = $1 AND kind = 'challenge_result' AND status = 'pending'""",
                attempt["id"],
            )
            if existing_req is not None:
                result = {"status": "pending", "request": dict(existing_req)}
            else:
                await conn.execute(
                    "UPDATE challenge_attempts SET status = 'pending_result', achieved_value = $1 WHERE id = $2",
                    achieved_value, attempt["id"],
                )
                req = await conn.fetchrow(
                    """INSERT INTO approval_requests
                           (kind, team_id, challenge_id, challenge_attempt_id, requested_value, status)
                       VALUES ('challenge_result', $1, $2, $3, $4, 'pending') RETURNING *""",
                    team_id, challenge_id, attempt["id"], json.dumps({"achieved_value": achieved_value}),
                )
                result = {"status": "pending", "request": dict(req)}
                events = [("notify_admin", team_id, "admin_pending")]

    await _fire(events)
    return result


def _compute_reward(challenge_type: str, reward_config: dict, called_shot_value: int | None,
                     achieved_value: int | None, fail_bonus_pct: float, target_balance: int | None) -> tuple[int, int | None]:
    """Returns (reward_amount, steal_amount_or_None). Positive reward is always
    credited to the acting team; steal_amount (if not None) is also debited
    from the target team."""
    bonus_mult = 1 + fail_bonus_pct / 100

    if challenge_type == "fixed":
        return round(reward_config.get("chips", 0) * bonus_mult), None

    if challenge_type == "variable":
        per_unit = reward_config.get("chips_per_unit", 0)
        achieved = achieved_value or 0
        if called_shot_value is not None and achieved < called_shot_value:
            return 0, None
        return round(achieved * per_unit * bonus_mult), None

    if challenge_type == "multiplier":
        pct = reward_config.get("multiplier_pct", 0) * bonus_mult
        base = target_balance or 0  # here target_balance carries the acting team's own balance
        return math.floor(max(0, base) * pct / 100), None

    if challenge_type == "steal":
        pct = reward_config.get("steal_pct", 0) * bonus_mult
        amount = math.floor(max(0, target_balance or 0) * pct / 100)
        return amount, amount

    return 0, None


async def resolve_challenge_result(request_id: int, admin_id: int, success: bool, achieved_value: int | None) -> dict:
    pool = get_pool()
    result: dict = {}
    events: list[tuple] = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            req = await conn.fetchrow("SELECT * FROM approval_requests WHERE id = $1 FOR UPDATE", request_id)
            if req is None:
                raise HTTPException(status_code=404, detail="找不到此請求")
            if req["kind"] != "challenge_result":
                raise HTTPException(status_code=400, detail="請求類型錯誤")
            if req["status"] != "pending":
                raise HTTPException(status_code=409, detail="此請求已被處理過")

            attempt = await conn.fetchrow(
                "SELECT * FROM challenge_attempts WHERE id = $1 FOR UPDATE", req["challenge_attempt_id"]
            )
            challenge = await conn.fetchrow("SELECT * FROM challenges WHERE id = $1", attempt["challenge_id"])
            team = await conn.fetchrow("SELECT * FROM teams WHERE id = $1 FOR UPDATE", attempt["team_id"])

            final_achieved = achieved_value if achieved_value is not None else attempt["achieved_value"]
            reward_config = challenge["reward_config"]
            if isinstance(reward_config, str):
                reward_config = json.loads(reward_config)

            target_row = None
            if attempt["target_team_id"] is not None:
                target_row = await conn.fetchrow(
                    "SELECT * FROM teams WHERE id = $1 FOR UPDATE", attempt["target_team_id"]
                )

            if not success:
                reward_amount, steal_amount = 0, None
            else:
                base_balance = team["chips_balance"] if challenge["type"] == "multiplier" else (
                    target_row["chips_balance"] if target_row else None
                )
                reward_amount, steal_amount = _compute_reward(
                    challenge["type"], reward_config, attempt["called_shot_value"],
                    final_achieved, float(attempt["fail_bonus_pct_locked"]), base_balance,
                )

            new_status = "success" if success else "failed"
            await conn.execute(
                """UPDATE challenge_attempts
                   SET status = $1, achieved_value = $2, reward_amount = $3, resolved_at = now()
                   WHERE id = $4""",
                new_status, final_achieved, reward_amount, attempt["id"],
            )
            await conn.execute(
                "UPDATE approval_requests SET status = 'approved', resolved_by = $1, resolved_at = now() WHERE id = $2",
                admin_id, request_id,
            )

            if reward_amount:
                await conn.execute("UPDATE teams SET chips_balance = chips_balance + $1 WHERE id = $2",
                                    reward_amount, attempt["team_id"])
            if steal_amount and target_row is not None:
                await conn.execute("UPDATE teams SET chips_balance = chips_balance - $1 WHERE id = $2",
                                    steal_amount, target_row["id"])

            new_team_balance_row = await conn.fetchrow("SELECT chips_balance FROM teams WHERE id = $1", attempt["team_id"])
            outcome_label = "成功" if success else "失敗"
            await _log(conn, attempt["team_id"], "admin", "challenge_result", challenge_id=challenge["id"],
                       chip_delta=reward_amount or None, resulting_balance=new_team_balance_row["chips_balance"],
                       message=f"任務「{challenge['name']}」{outcome_label}，獲得 {reward_amount} 枚代幣")

            events = [("notify_team", attempt["team_id"], "team_update"), ("notify_admin", attempt["team_id"], "admin_pending")]

            if steal_amount and target_row is not None:
                target_new_balance = await conn.fetchrow("SELECT chips_balance FROM teams WHERE id = $1", target_row["id"])
                await _log(conn, target_row["id"], "admin", "challenge_stolen", challenge_id=challenge["id"],
                           chip_delta=-steal_amount, resulting_balance=target_new_balance["chips_balance"],
                           message=f"被「{challenge['name']}」偷走 {steal_amount} 枚代幣")
                events.append(("notify_team", target_row["id"], "team_update"))

            if reward_amount:
                events.append(("broadcast_global", "ranking_update"))

            # Pool lifecycle: retire once every active team has used its one attempt on this
            # challenge, then top up the active pool from the queued backlog.
            active_team_count = await conn.fetchval("SELECT COUNT(*) FROM teams WHERE active = TRUE")
            resolved_count = await conn.fetchval(
                "SELECT COUNT(*) FROM challenge_attempts WHERE challenge_id = $1 AND status IN ('success','failed')",
                challenge["id"],
            )
            if resolved_count >= active_team_count:
                await conn.execute("UPDATE challenges SET pool_state = 'retired' WHERE id = $1", challenge["id"])
                await _refill_pool(conn)
                events.append(("broadcast_global", "challenge_pool"))

    await _fire(events)
    return result


async def _refill_pool(conn) -> None:
    cfg = await conn.fetchrow("SELECT * FROM game_config WHERE id = 1")
    active_count = await conn.fetchval("SELECT COUNT(*) FROM challenges WHERE pool_state = 'active'")
    slots = min(cfg["challenge_pool_refill"], cfg["challenge_pool_max"] - active_count)
    if slots <= 0:
        return
    candidates = await conn.fetch("SELECT id FROM challenges WHERE pool_state = 'queued'")
    if not candidates:
        return
    chosen = random.sample(candidates, k=min(slots, len(candidates)))
    for row in chosen:
        await conn.execute("UPDATE challenges SET pool_state = 'active' WHERE id = $1", row["id"])


async def activate_initial_pool() -> None:
    """Called by superadmin when kicking off the challenge pool for the first time."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            cfg = await conn.fetchrow("SELECT * FROM game_config WHERE id = 1")
            active_count = await conn.fetchval("SELECT COUNT(*) FROM challenges WHERE pool_state = 'active'")
            slots = cfg["challenge_pool_initial"] - active_count
            if slots > 0:
                candidates = await conn.fetch("SELECT id FROM challenges WHERE pool_state = 'queued'")
                chosen = random.sample(candidates, k=min(slots, len(candidates))) if candidates else []
                for row in chosen:
                    await conn.execute("UPDATE challenges SET pool_state = 'active' WHERE id = $1", row["id"])
    await manager.broadcast_global("challenge_pool")


# ---------------------------------------------------------------------------
# End-of-game sweep for attempts left dangling when the clock runs out
# ---------------------------------------------------------------------------

async def sweep_expired_attempts() -> None:
    phase = await get_phase()
    if phase["phase"] != "ended":
        return
    pool = get_pool()
    touched = False
    async with pool.acquire() as conn:
        async with conn.transaction():
            stuck = await conn.fetch(
                "SELECT * FROM challenge_attempts WHERE status IN ('in_progress', 'pending_result') FOR UPDATE"
            )
            for a in stuck:
                touched = True
                await conn.execute(
                    "UPDATE challenge_attempts SET status = 'failed', reward_amount = 0, resolved_at = now() WHERE id = $1",
                    a["id"],
                )
                await conn.execute(
                    "UPDATE approval_requests SET status = 'stale' WHERE challenge_attempt_id = $1 AND status = 'pending'",
                    a["id"],
                )
                await _log(conn, a["team_id"], "system", "challenge_auto_failed", challenge_id=a["challenge_id"],
                            message="遊戲時間結束，任務自動判定為失敗")
            pending_actions = await conn.fetch(
                "SELECT * FROM approval_requests WHERE status = 'pending' AND kind IN ('claim', 'topup') FOR UPDATE"
            )
            for r in pending_actions:
                touched = True
                await conn.execute("UPDATE approval_requests SET status = 'stale' WHERE id = $1", r["id"])
    if touched:
        await manager.broadcast_global("ranking_update")


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def get_ranking() -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT t.id, t.name, t.color_hex, t.meeting_station_id, t.chips_balance, t.active,
               COALESCE(sc.cnt, 0) AS stations_owned
        FROM teams t
        LEFT JOIN (
            SELECT owner_team_id, COUNT(*) AS cnt
            FROM station_claims
            WHERE owner_team_id IS NOT NULL
            GROUP BY owner_team_id
        ) sc ON sc.owner_team_id = t.id
        WHERE t.active = TRUE
        ORDER BY stations_owned DESC, t.chips_balance DESC, t.id ASC
        """
    )
    ranking = []
    prev_key = None
    rank = 0
    for i, r in enumerate(rows):
        key = (r["stations_owned"], r["chips_balance"])
        if key != prev_key:
            rank = i + 1
        prev_key = key
        d = dict(r)
        d["rank"] = rank
        ranking.append(d)
    return ranking


async def get_pending_for_team(team_id: int) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM approval_requests WHERE team_id = $1 AND status = 'pending' ORDER BY created_at",
        team_id,
    )
    return [dict(r) for r in rows]
