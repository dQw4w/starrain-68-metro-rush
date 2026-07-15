import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from db import close_pool, get_pool, init_pool
from game_logic import sweep_expired_attempts
from migrate import run_migrations
from routers import admin, auth, challenges, config, realtime, stations, team

_sweep_task: asyncio.Task | None = None


async def _sweep_loop():
    while True:
        try:
            await sweep_expired_attempts()
        except Exception:
            logger.exception("sweep_expired_attempts failed")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sweep_task
    await init_pool()
    await run_migrations()
    _sweep_task = asyncio.create_task(_sweep_loop())
    yield
    _sweep_task.cancel()
    await close_pool()


app = FastAPI(title="Metro Rush", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(config.router)
app.include_router(stations.router)
app.include_router(challenges.router)
app.include_router(team.router)
app.include_router(admin.router)
app.include_router(realtime.router)


@app.get("/health")
async def health():
    try:
        await get_pool().fetchval("SELECT 1")
        return {"ok": True}
    except Exception:
        return JSONResponse(status_code=503, content={"ok": False})


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
