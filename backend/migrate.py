import secrets
from pathlib import Path
from loguru import logger
from db import get_pool
from seed_stations import seed
from seed_challenges import seed as seed_challenges

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def run_migrations() -> None:
    pool = get_pool()
    sql = _SCHEMA_PATH.read_text()
    async with pool.acquire() as conn:
        await conn.execute(sql)
    logger.info("Schema migration complete.")
    await _ensure_superadmin()
    await _backfill_admin_links()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await seed(conn)
            await seed_challenges(conn)


async def _backfill_admin_links() -> None:
    """Any team admin created before admin_share_token existed gets one now,
    so a link-based flow rolled out mid-project doesn't strand old teams."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id FROM admins WHERE team_id IS NOT NULL AND admin_share_token IS NULL"
    )
    for row in rows:
        await pool.execute(
            "UPDATE admins SET admin_share_token = $1 WHERE id = $2",
            secrets.token_urlsafe(24), row["id"],
        )
    if rows:
        logger.info(f"Backfilled admin_share_token for {len(rows)} team admin(s).")


async def _ensure_superadmin() -> None:
    """Just an id anchor for sessions / approval_requests.resolved_by — the
    PIN itself is never stored here (see auth.verify_superadmin_pin), so
    unlike everything else this function used to do, there's no PIN to keep
    in sync: SUPERADMIN_BOOTSTRAP_PIN is read live on every login."""
    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM admins WHERE team_id IS NULL LIMIT 1"
        )
        if existing is None:
            await conn.execute(
                "INSERT INTO admins (team_id, display_name) VALUES (NULL, $1)",
                "超級管理員",
            )
            logger.info("Seeded super-admin row.")
