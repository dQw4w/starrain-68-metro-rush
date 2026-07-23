"""Seeds ~36 placeholder challenges scattered at real Taipei-area landmarks.

Every challenge's `description` is a literal "TBD" placeholder (to be written
later) but each one already has a real reward and location, so the pool is
fully playable as-is. Exactly 3 start `pool_state='active'` — all `type='fixed'`
(constant-value reward) per the game's opening-pool rule; the rest start
'queued' and enter play later via activate_initial_pool()/_refill_pool() in
game_logic.py.

`seed()` is idempotent and upserts by `name` (see idx_challenges_name in
schema.sql). It deliberately never overwrites `pool_state` on conflict, so
redeploying mid-event never resets a challenge that's already gone
active/retired — only name/type/reward/location edits here take effect.
Runs automatically on every backend startup (see migrate.py).
"""
import json

TBD = "TBD"

# name, type, reward_config, location_name, lat, lng, initial_pool_state
_CHALLENGES: list[tuple] = [
    ("台北101登高任務", "fixed", {"chips": 25}, "台北101", 25.0339, 121.5645, "active"),
    ("中正紀念堂衛兵交接觀察", "variable", {"chips_per_unit": 6, "unit_label": "分鐘"}, "中正紀念堂", 25.0359, 121.5222, "queued"),
    ("龍山寺祈福任務", "steal", {"steal_pct": 30}, "龍山寺", 25.0367, 121.4998, "queued"),
    ("士林夜市美食挑戰", "multiplier", {"multiplier_pct": 15}, "士林夜市", 25.0880, 121.5240, "queued"),
    ("饒河街夜市任務", "fixed", {"chips": 20}, "饒河街觀光夜市", 25.0504, 121.5772, "active"),
    ("西門町尋寶任務", "variable", {"chips_per_unit": 8, "unit_label": "件"}, "西門町", 25.0421, 121.5079, "queued"),
    ("大稻埕碼頭日落任務", "steal", {"steal_pct": 25}, "大稻埕碼頭", 25.0554, 121.5088, "queued"),
    ("迪化街年貨任務", "multiplier", {"multiplier_pct": 20}, "迪化街", 25.0557, 121.5100, "queued"),
    ("國父紀念館廣場任務", "fixed", {"chips": 30}, "國父紀念館", 25.0403, 121.5578, "active"),
    ("貓空纜車任務", "variable", {"chips_per_unit": 10, "unit_label": "站"}, "貓空", 24.9877, 121.5824, "queued"),
    ("象山夜景任務", "steal", {"steal_pct": 35}, "象山", 25.0272, 121.5706, "queued"),
    ("陽明山任務", "multiplier", {"multiplier_pct": 25}, "陽明山", 25.1552, 121.5391, "queued"),
    ("淡水老街小吃任務", "fixed", {"chips": 18}, "淡水老街", 25.1700, 121.4405, "queued"),
    ("紅毛城歷史任務", "variable", {"chips_per_unit": 7, "unit_label": "題"}, "紅毛城", 25.1755, 121.4344, "queued"),
    ("北投溫泉博物館任務", "steal", {"steal_pct": 20}, "北投溫泉博物館", 25.1367, 121.5079, "queued"),
    ("華山1914文創任務", "multiplier", {"multiplier_pct": 18}, "華山1914文創園區", 25.0443, 121.5296, "queued"),
    ("松山文創園區任務", "fixed", {"chips": 22}, "松山文創園區", 25.0442, 121.5602, "queued"),
    ("華西街觀光夜市任務", "variable", {"chips_per_unit": 9, "unit_label": "攤"}, "華西街觀光夜市", 25.0369, 121.4990, "queued"),
    ("臨江街夜市任務", "steal", {"steal_pct": 28}, "臨江街夜市", 25.0264, 121.5490, "queued"),
    ("士林官邸花園任務", "multiplier", {"multiplier_pct": 12}, "士林官邸", 25.0942, 121.5252, "queued"),
    ("圓山大飯店任務", "fixed", {"chips": 28}, "圓山大飯店", 25.0798, 121.5218, "queued"),
    ("台北市立美術館任務", "variable", {"chips_per_unit": 6, "unit_label": "件"}, "台北市立美術館", 25.0716, 121.5243, "queued"),
    ("故宮博物院任務", "steal", {"steal_pct": 40}, "國立故宮博物院", 25.1024, 121.5486, "queued"),
    ("東吳大學校園任務", "multiplier", {"multiplier_pct": 15}, "東吳大學", 25.0967, 121.5391, "queued"),
    ("台大校門任務", "fixed", {"chips": 16}, "國立台灣大學", 25.0174, 121.5397, "queued"),
    ("師大夜市小吃任務", "variable", {"chips_per_unit": 5, "unit_label": "樣"}, "師大夜市", 25.0264, 121.5292, "queued"),
    ("公館夜市任務", "steal", {"steal_pct": 22}, "公館夜市", 25.0148, 121.5344, "queued"),
    ("建國假日花市任務", "multiplier", {"multiplier_pct": 10}, "建國假日花市", 25.0330, 121.5406, "queued"),
    ("光華商場任務", "fixed", {"chips": 24}, "光華商場", 25.0453, 121.5340, "queued"),
    ("台北市政府廣場任務", "variable", {"chips_per_unit": 11, "unit_label": "步"}, "台北市政府", 25.0375, 121.5645, "queued"),
    ("松山機場觀景台任務", "steal", {"steal_pct": 32}, "松山機場觀景台", 25.0637, 121.5519, "queued"),
    ("大湖公園任務", "multiplier", {"multiplier_pct": 22}, "大湖公園", 25.0836, 121.6023, "queued"),
    ("關渡自然公園任務", "fixed", {"chips": 26}, "關渡自然公園", 25.1225, 121.4606, "queued"),
    ("天元宮任務", "variable", {"chips_per_unit": 12, "unit_label": "階"}, "天元宮", 25.1928, 121.4356, "queued"),
    ("剝皮寮歷史街區任務", "steal", {"steal_pct": 26}, "剝皮寮歷史街區", 25.0358, 121.5028, "queued"),
    ("台北植物園任務", "multiplier", {"multiplier_pct": 14}, "台北植物園", 25.0316, 121.5106, "queued"),
]


async def seed(conn) -> None:
    """Idempotent upsert by `name`. `pool_state` is intentionally absent from
    the ON CONFLICT SET clause — only set on first INSERT — so redeploying
    mid-event never resets a challenge that's already gone active/retired.

    `name` is the map-visible title (location-flavored only, e.g. "饒河街任務")
    — `inner_title` is the real/flavor title, hidden alongside `description`
    until a team's attempt is approved to start."""
    for name, ctype, reward_config, location_name, lat, lng, initial_state in _CHALLENGES:
        await conn.execute(
            """INSERT INTO challenges (name, inner_title, description, type, reward_config, location_name, lat, lng, pool_state)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
               ON CONFLICT (name) DO UPDATE
               SET inner_title = EXCLUDED.inner_title, description = EXCLUDED.description, type = EXCLUDED.type,
                   reward_config = EXCLUDED.reward_config, location_name = EXCLUDED.location_name,
                   lat = EXCLUDED.lat, lng = EXCLUDED.lng""",
            name, TBD, TBD, ctype, json.dumps(reward_config), location_name, lat, lng, initial_state,
        )
