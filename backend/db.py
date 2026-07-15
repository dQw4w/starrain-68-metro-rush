import asyncpg
from loguru import logger
from config import DATABASE_URL

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    logger.info("Connecting to Postgres...")
    # statement_cache_size=0: required if DATABASE_URL ever points at a
    # transaction-mode pooler (e.g. Supabase's "Transaction pooler"), which is
    # incompatible with asyncpg's server-side prepared statements. Harmless
    # against a direct/session connection too.
    _pool = await asyncpg.create_pool(
        DATABASE_URL, statement_cache_size=0, min_size=1, max_size=10
    )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    assert _pool is not None, "DB pool not initialized"
    return _pool
