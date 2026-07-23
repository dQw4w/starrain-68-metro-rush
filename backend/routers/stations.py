from fastapi import APIRouter, Depends, HTTPException

from auth import AdminIdentity, require_superadmin
from db import get_pool
from models import (
    Line,
    LineCreate,
    LineStationOrderEntry,
    MapData,
    PublicGameConfig,
    Station,
    StationClaim,
    StationCreate,
    StationUpdate,
)

router = APIRouter(tags=["map"])


async def _load_map_data() -> MapData:
    pool = get_pool()
    lines = await pool.fetch("SELECT * FROM lines ORDER BY sort_order")
    stations = await pool.fetch("SELECT * FROM stations ORDER BY id")
    station_lines = await pool.fetch("SELECT station_id, line_id, sequence FROM station_lines ORDER BY line_id, sequence")
    waypoints = await pool.fetch("SELECT line_id, sequence, lat, lng FROM line_waypoints ORDER BY line_id, sequence")
    claims = await pool.fetch("SELECT * FROM station_claims")

    stations_by_id = {s["id"]: s for s in stations}
    line_map: dict[int, list[int]] = {}
    # (sequence, lat, lng) per line, merging real stations and invisible
    # waypoints so the frontend gets one ready-to-draw ordered point list.
    line_points: dict[str, list[tuple[int, float, float]]] = {}
    for sl in station_lines:
        line_map.setdefault(sl["station_id"], []).append(sl["line_id"])
        st = stations_by_id[sl["station_id"]]
        line_points.setdefault(str(sl["line_id"]), []).append((sl["sequence"], st["lat"], st["lng"]))
    for wp in waypoints:
        line_points.setdefault(str(wp["line_id"]), []).append((wp["sequence"], wp["lat"], wp["lng"]))

    line_paths = {
        line_id: [[lat, lng] for _, lat, lng in sorted(points, key=lambda p: p[0])]
        for line_id, points in line_points.items()
    }

    return MapData(
        lines=[Line(**dict(l)) for l in lines],
        stations=[
            Station(**dict(s), line_ids=line_map.get(s["id"], []))
            for s in stations
        ],
        claims=[StationClaim(**dict(c)) for c in claims],
        line_paths=line_paths,
    )


@router.get("/api/map", response_model=MapData)
async def get_map():
    return await _load_map_data()


@router.get("/api/config/public", response_model=PublicGameConfig)
async def public_game_config():
    """Non-sensitive config fields team clients need to render UI (e.g. the
    legal claim/top-up deposit range), without needing admin auth."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT starting_chips, max_deposit_per_visit, fail_bonus_step_pct FROM game_config WHERE id = 1"
    )
    return PublicGameConfig(**dict(row))


# --- Superadmin geo data management -------------------------------------------------

@router.get("/api/superadmin/line-station-order", response_model=dict[str, list[LineStationOrderEntry]])
async def line_station_order(_: AdminIdentity = Depends(require_superadmin)):
    """Ordered station list per line (id/name/coords/sequence) — used by the
    line-waypoint editor to build the "adjacent station pair" picker; not
    needed by any gameplay page (those just consume /api/map's line_paths)."""
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT sl.line_id, sl.sequence, s.id AS station_id, s.name_zh, s.lat, s.lng
        FROM station_lines sl
        JOIN stations s ON s.id = sl.station_id
        ORDER BY sl.line_id, sl.sequence
        """
    )
    result: dict[str, list[LineStationOrderEntry]] = {}
    for r in rows:
        result.setdefault(str(r["line_id"]), []).append(
            LineStationOrderEntry(
                station_id=r["station_id"], name_zh=r["name_zh"],
                lat=r["lat"], lng=r["lng"], sequence=r["sequence"],
            )
        )
    return result

@router.post("/api/superadmin/lines", response_model=Line)
async def create_line(body: LineCreate, _: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    row = await pool.fetchrow(
        "INSERT INTO lines (code, name_zh, name_en, color_hex, sort_order) VALUES ($1,$2,$3,$4,$5) RETURNING *",
        body.code, body.name_zh, body.name_en, body.color_hex, body.sort_order,
    )
    return Line(**dict(row))


@router.get("/api/superadmin/lines", response_model=list[Line])
async def list_lines(_: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    rows = await pool.fetch("SELECT * FROM lines ORDER BY sort_order")
    return [Line(**dict(r)) for r in rows]


@router.post("/api/superadmin/stations", response_model=Station)
async def create_station(body: StationCreate, _: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "INSERT INTO stations (name_zh, name_en, lat, lng) VALUES ($1,$2,$3,$4) RETURNING *",
                body.name_zh, body.name_en, body.lat, body.lng,
            )
            for entry in body.lines:
                await conn.execute(
                    "INSERT INTO station_lines (station_id, line_id, sequence) VALUES ($1,$2,$3) "
                    "ON CONFLICT (station_id, line_id) DO UPDATE SET sequence = EXCLUDED.sequence",
                    row["id"], entry["line_id"], entry.get("sequence", 0),
                )
            await conn.execute(
                "INSERT INTO station_claims (station_id, value) VALUES ($1, 0) ON CONFLICT DO NOTHING",
                row["id"],
            )
    return Station(**dict(row), line_ids=[e["line_id"] for e in body.lines])


@router.put("/api/superadmin/stations/{station_id}", response_model=Station)
async def update_station(station_id: int, body: StationUpdate, _: AdminIdentity = Depends(require_superadmin)):
    pool = get_pool()
    fields = body.model_dump(exclude_unset=True)
    if fields:
        set_clause = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(fields))
        values = list(fields.values())
        row = await pool.fetchrow(
            f"UPDATE stations SET {set_clause} WHERE id = ${len(values) + 1} RETURNING *",
            *values, station_id,
        )
    else:
        row = await pool.fetchrow("SELECT * FROM stations WHERE id = $1", station_id)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到此車站")
    line_ids = [r["line_id"] for r in await pool.fetch(
        "SELECT line_id FROM station_lines WHERE station_id = $1", station_id
    )]
    return Station(**dict(row), line_ids=line_ids)
