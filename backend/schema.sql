-- Metro Rush schema. Idempotent: safe to run on every startup.

CREATE TABLE IF NOT EXISTS game_config (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    team_count INT NOT NULL DEFAULT 2,
    game_date DATE NOT NULL DEFAULT CURRENT_DATE,
    start_time TIME NOT NULL DEFAULT '09:00',
    end_time TIME NOT NULL DEFAULT '18:00',
    lunch_start TIME NOT NULL DEFAULT '12:00',
    lunch_end TIME NOT NULL DEFAULT '13:00',
    starting_chips INT NOT NULL DEFAULT 50,
    max_deposit_per_visit INT NOT NULL DEFAULT 5,
    fail_bonus_step_pct NUMERIC NOT NULL DEFAULT 25,
    challenge_pool_initial INT NOT NULL DEFAULT 3,
    challenge_pool_refill INT NOT NULL DEFAULT 2,
    challenge_pool_max INT NOT NULL DEFAULT 10,
    override_status TEXT NOT NULL DEFAULT 'auto' CHECK (override_status IN ('auto', 'paused', 'force_ended')),
    locked BOOLEAN NOT NULL DEFAULT FALSE
);
INSERT INTO game_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS lines (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name_zh TEXT NOT NULL,
    name_en TEXT NOT NULL,
    color_hex TEXT NOT NULL,
    sort_order INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stations (
    id SERIAL PRIMARY KEY,
    name_zh TEXT NOT NULL,
    name_en TEXT NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL
);

-- Lets seed_stations.py upsert by name_zh instead of inserting a fresh
-- duplicate row every time the seed data changes.
CREATE UNIQUE INDEX IF NOT EXISTS idx_stations_name_zh ON stations (name_zh);

CREATE TABLE IF NOT EXISTS station_lines (
    station_id INT NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    line_id INT NOT NULL REFERENCES lines(id) ON DELETE CASCADE,
    sequence INT NOT NULL,
    PRIMARY KEY (station_id, line_id)
);

-- Invisible "shape points" between two consecutive stations on a line, so the
-- drawn polyline can follow the real track curvature instead of a straight
-- line between station dots. Not real stations: not clickable, no claims, no
-- FK from anything else. Fully rewritten by seed_stations.py on every boot
-- (delete+reinsert per line), so there's nothing to migrate by hand — just
-- edit _LINE_WAYPOINTS in seed_stations.py and redeploy.
CREATE TABLE IF NOT EXISTS line_waypoints (
    id SERIAL PRIMARY KEY,
    line_id INT NOT NULL REFERENCES lines(id) ON DELETE CASCADE,
    sequence INT NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_line_waypoints_line ON line_waypoints (line_id, sequence);

CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    color_hex TEXT NOT NULL DEFAULT '#3B82F6',
    meeting_station_id INT REFERENCES stations(id),
    chips_balance INT NOT NULL DEFAULT 50,
    share_token TEXT UNIQUE NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Team admin auth now lives entirely on the admins row (admin_share_token) —
-- this was a duplicate that was never actually read for auth.
ALTER TABLE teams DROP COLUMN IF EXISTS admin_pin_hash;

CREATE TABLE IF NOT EXISTS admins (
    id SERIAL PRIMARY KEY,
    team_id INT REFERENCES teams(id),
    display_name TEXT NOT NULL,
    -- Super admin (team_id IS NULL) logs in with a PIN. Team admins instead
    -- get a private, unguessable link (admin_share_token) — no PIN, no login
    -- form; visiting the link grants a session directly.
    pin_hash TEXT,
    admin_share_token TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE admins ALTER COLUMN pin_hash DROP NOT NULL;
ALTER TABLE admins ADD COLUMN IF NOT EXISTS admin_share_token TEXT UNIQUE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_admins_one_per_team ON admins (team_id) WHERE team_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS admin_sessions (
    token TEXT PRIMARY KEY,
    admin_id INT NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS station_claims (
    station_id INT PRIMARY KEY REFERENCES stations(id) ON DELETE CASCADE,
    owner_team_id INT REFERENCES teams(id),
    value INT NOT NULL DEFAULT 0 CHECK (value >= 0),
    -- Ceiling for `value` while the CURRENT owner holds this station, fixed at
    -- (value of the previous owner at the moment of takeover) + max_deposit_per_visit.
    -- Only a claim (ownership change) recomputes this; top-ups never touch it.
    cap INT NOT NULL DEFAULT 5,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- station_claims.value previously had an upper bound of 5 baked into the
-- CHECK constraint; the cap is now per-row (see `cap` above) and grows with
-- each takeover, so any fixed upper bound has to come off existing rows too.
ALTER TABLE station_claims DROP CONSTRAINT IF EXISTS station_claims_value_check;
ALTER TABLE station_claims ADD CONSTRAINT station_claims_value_check CHECK (value >= 0);
ALTER TABLE station_claims ADD COLUMN IF NOT EXISTS cap INT NOT NULL DEFAULT 5;

CREATE TABLE IF NOT EXISTS challenges (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('fixed', 'variable', 'steal', 'multiplier')),
    reward_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    location_name TEXT,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    image_url TEXT,
    pool_state TEXT NOT NULL DEFAULT 'queued' CHECK (pool_state IN ('queued', 'active', 'retired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lets seed_challenges.py upsert by name instead of inserting a fresh
-- duplicate row every time the seed data changes.
CREATE UNIQUE INDEX IF NOT EXISTS idx_challenges_name ON challenges (name);

CREATE TABLE IF NOT EXISTS challenge_attempts (
    id SERIAL PRIMARY KEY,
    challenge_id INT NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
    team_id INT NOT NULL REFERENCES teams(id),
    status TEXT NOT NULL DEFAULT 'pending_start_approval' CHECK (
        status IN ('pending_start_approval', 'in_progress', 'pending_result', 'success', 'failed')
    ),
    called_shot_value INT,
    achieved_value INT,
    target_team_id INT REFERENCES teams(id),
    fail_bonus_pct_locked NUMERIC NOT NULL DEFAULT 0,
    reward_amount INT,
    started_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (challenge_id, team_id)
);

CREATE TABLE IF NOT EXISTS approval_requests (
    id SERIAL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('claim', 'topup', 'challenge_start', 'challenge_result')),
    team_id INT NOT NULL REFERENCES teams(id),
    station_id INT REFERENCES stations(id),
    challenge_id INT REFERENCES challenges(id),
    challenge_attempt_id INT REFERENCES challenge_attempts(id),
    requested_by TEXT,
    requested_value JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied', 'stale')),
    resolved_by INT REFERENCES admins(id),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS action_log (
    id SERIAL PRIMARY KEY,
    team_id INT NOT NULL REFERENCES teams(id),
    actor TEXT NOT NULL,
    action_type TEXT NOT NULL,
    station_id INT REFERENCES stations(id),
    challenge_id INT REFERENCES challenges(id),
    chip_delta INT,
    resulting_balance INT,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS device_positions (
    team_id INT NOT NULL REFERENCES teams(id),
    device_id TEXT NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, device_id)
);

CREATE INDEX IF NOT EXISTS idx_action_log_team ON action_log (team_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_approval_requests_pending ON approval_requests (team_id, status);
CREATE INDEX IF NOT EXISTS idx_challenge_attempts_challenge ON challenge_attempts (challenge_id);
