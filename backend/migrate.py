import secrets
from pathlib import Path
from loguru import logger
from db import get_pool
from auth import hash_pin
from config import SUPERADMIN_BOOTSTRAP_PIN
from seed_stations import seed

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
    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM admins WHERE team_id IS NULL LIMIT 1"
        )
        if existing is None:
            await conn.execute(
                "INSERT INTO admins (team_id, display_name, pin_hash) VALUES (NULL, $1, $2)",
                "超級管理員",
                hash_pin(SUPERADMIN_BOOTSTRAP_PIN),
            )
            logger.warning(
                f"Seeded super-admin with bootstrap PIN {SUPERADMIN_BOOTSTRAP_PIN!r} "
                "— change SUPERADMIN_BOOTSTRAP_PIN in .env before a real event."
            )
