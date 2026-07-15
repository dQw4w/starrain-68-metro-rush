from pathlib import Path
from loguru import logger
from db import get_pool
from auth import hash_pin
from config import SUPERADMIN_BOOTSTRAP_PIN
from seed_stations import seed_if_empty

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def run_migrations() -> None:
    pool = get_pool()
    sql = _SCHEMA_PATH.read_text()
    async with pool.acquire() as conn:
        await conn.execute(sql)
    logger.info("Schema migration complete.")
    await _ensure_superadmin()
    await seed_if_empty(pool)


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
