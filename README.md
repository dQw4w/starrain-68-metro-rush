# Metro Rush

A live, one-day, phone-based team competition where teams physically visit
real Taipei Metro (TRTC) stations and claim them using a chip currency
earned through location-based challenges — refereed in real time by a human
admin embedded with each team. A remake of *Jet Lag: The Game* S17
("Taiwan: Rail Rush"), reworked for the Taipei Metro network. Game rules are
in [outline.txt](outline.txt).

## Stack

- **Backend**: FastAPI + `asyncpg` (direct Postgres access, real transactions
  for the chip economy) + a WebSocket layer for live admin-approval popups.
- **Frontend**: React + Vite + TypeScript + Tailwind + Leaflet (real
  OpenStreetMap-based map with the actual TRTC line/station geometry).
- **Database**: Postgres. Locally, a plain Postgres container
  (`docker-compose.yml`'s `db` service). In production, point
  `DATABASE_URL` at a Supabase Postgres project (Supabase is just hosted
  Postgres here — no Supabase-specific SDK is used).

## Local development

```bash
cp .env.example .env          # defaults already match docker-compose's db service
docker compose up -d db       # starts local Postgres on localhost:5433

cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload     # http://localhost:8000

cd ../frontend
npm install
npm run dev                   # http://localhost:5173, proxies /api + /ws to :8000
```

On first boot, the backend auto-runs `schema.sql` and seeds the full TRTC
network (6 lines, ~117 stations — see `backend/seed_stations.py`) plus a
single super-admin account using the PIN in `SUPERADMIN_BOOTSTRAP_PIN`
(default `0000` — **change this before a real event**). Log in at
`/admin/login` → 總管理員 to create teams (each team gets a share link
`/team/{token}` and its own admin PIN) and set up challenges.

Station coordinates: ~108 of them come from real GIS open data; the
Circular Line (環狀線, opened 2020) uses hand-estimated coordinates since
that line predates the dataset used — correct these via the super-admin
station editor if precision matters for your event.

## Production deployment

Two things the old zoo-game version of this repo didn't need, and you will:

1. **A real Postgres database.** Create a Supabase project and set
   `DATABASE_URL` in `.env` to its **direct or session** connection string
   (Project Settings → Database) — not the "Transaction pooler" string,
   which is incompatible with `asyncpg`'s prepared statements.
2. **An always-on, internet-reachable host.** Unlike the old app (a laptop
   on venue WiFi was fine for a single-venue event), Metro Rush is a
   city-wide game — teams are on cellular data all over Taipei, not a
   shared LAN. Deploy the Docker image (`build.sh`) to a small VM or a
   platform like Fly/Railway with a persistent instance (the WebSocket
   connection manager is in-memory and single-process, so it needs one
   long-lived container, not an autoscaled/serverless one).

```bash
./build.sh     # builds the frontend + backend into one Docker image
./up.sh        # docker compose up (also starts the local `db` service if DATABASE_URL isn't overridden)
```

For production, override `DATABASE_URL` in `.env` to point at Supabase
instead of the local `db` service.

## Project layout

- `backend/schema.sql` — full DB schema (idempotent, runs on every boot).
- `backend/game_logic.py` — the transactional game rules: station claim /
  top-up / toll, challenge attempt lifecycle, fail-bonus scaling, ranking.
- `backend/ws.py` + `backend/routers/realtime.py` — the WebSocket layer
  behind the live admin-approval popups.
- `backend/seed_stations.py` — TRTC network seed data.
- `frontend/src/pages/TeamPage.tsx` — the team's map/log/ranking/GPS view.
- `frontend/src/pages/TeamAdminPage.tsx` — the per-team admin approval queue.
- `frontend/src/pages/SuperAdminPage.tsx` — global config/teams/challenges.
