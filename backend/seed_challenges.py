"""Seeds ~36 placeholder challenges scattered at real Taipei-area landmarks,
plus a growing set of fully-written real challenges (see _CONTENT below).

Every challenge's `description` defaults to a literal "TBD" placeholder (to
be written later) but each one already has a real reward and location, so
the pool is fully playable as-is even before real content is written.
Exactly 3 start `pool_state='active'` — all `type='fixed'` (constant-value
reward) per the game's opening-pool rule; the rest start 'queued' and enter
play later via activate_initial_pool()/_refill_pool() in game_logic.py.

`seed()` is idempotent and upserts by `name` (see idx_challenges_name in
schema.sql). It deliberately never overwrites `pool_state` on conflict, so
redeploying mid-event never resets a challenge that's already gone
active/retired — only name/type/reward/location/content edits here take
effect. Runs automatically on every backend startup (see migrate.py).
"""
import json

TBD = "TBD"

# name -> (inner_title, description). Real/flavor title + team-facing task
# text, only revealed to a team once their attempt is approved to start (see
# routers/challenges.py). Any challenge whose name isn't listed here still
# gets the TBD/TBD placeholder. Keep any admin-only answer key OUT of here
# (description reaches the attempting team) — put it in a comment next to
# the challenge's entry in _CHALLENGES instead, or hand it to admins
# out-of-band; either way it must never round-trip through the DB/API.
_CONTENT: dict[str, tuple[str, str]] = {
    "台大二活任務": (
        "台大社團知多少",
        "限時10分鐘，請上去2活的8-10樓，去看二活有哪些各社辦，可以分工合作分頭行動。"
        "結束後回到此地，隨隊管理員將會講出7個社團的名字，你們要告訴他二活是否存在該社團的社辦。"
        "回答時禁止看手機或是筆記。",
    ),
    "西門動漫朝聖任務": (
        "西門聖地巡禮：尋找元氣穗乃果",
        "高坂穂乃果是本活動主辦人最喜歡的動漫角色之一，西門町是二次元動漫文化的聖地，想必一定有賣她的周邊。"
        "請找到一個高坂穂乃果的周邊，價格300元（含）以內，把它買下來"
        "（活動結束後請把周邊轉交給主辦人，主辦人會給你錢）。"
        "周邊可為同人或是官方商品，但周邊上不得出現其他角色的圖案。",
    ),
    "建成圓環任務": (
        "許願圓環：喊出你的極限數字",
        "恭喜你們來到了台北市最具代表性且還沒有被拆掉的圓環之一，建成圓環。"
        "現在，請大家也圍成一個圓，依照逆時針的方向輪流數數，並且決定好誰先，從1數到你們喊出的目標數字"
        "（須介於30~100之間，開始任務前自行決定）。只是現在星雨是68期，所以遇到6的倍數、8的倍數，"
        "或是數字中包含6或8，請改成拍手而不把數字數出來。如果成功數到你們喊出的數字，就獲得同額的代幣數量，"
        "但只要有一個人搞砸，或是停頓超過5秒鐘，就任務失敗，一枚都拿不到。",
    ),
    "台北地下街任務": (
        "步步為贏：丈量地下街",
        "Y區地下街是台北市最繁華的地下街之一，裡面有許多動漫遊戲相關的店家，也有販售東南亞異國料理。"
        "現在，直到任務結束為止都禁止使用手機與網路，也禁止問其他人。請測量台北地下街的總長，"
        "誤差需在100公尺（含）以內。",
    ),
    "葫洲站早午餐任務": (
        "巷口的牛肉麵回憶",
        "主辦人的家就在葫洲站附近。雖然主辦人總是笑稱內湖是美食沙漠，但這裡也還是有很多從小吃到大的好滋味。"
        "請在附近找到一間有賣牛肉麵的平價台式早午餐店，並在店家前面拍合照！"
        "只有一次機會，如果找錯家就算任務失敗。",
    ),
    "美麗華摩天輪任務": (
        "陪你爬上摩天輪的路",
        "歡迎來到美麗華，這裡有著台灣最美的摩天輪之一。但主辦人同樣也很喜歡美麗華室外的樓梯，"
        "且從地面層沿著樓梯爬到最上面就能抵達摩天輪的所在處！所以，主辦人想讓你們親自體驗爬這座樓梯的感覺。"
        "請大家在樓梯的地面層處預備、限時10分鐘，事先決定好要爬幾趟。一趟為一上一下，"
        "需抵達摩天輪所在的樓層才能折返，且所有組員都必須同步完成。"
        "如果在時間內達成你們指定的趟數，則可獲得代幣，若無法，即使只是差1秒或有1個人差了1格樓梯，任務失敗。",
    ),
    "忠孝敦化街機任務": (
        "東區裡的舞步傳說",
        "如圖，Dance Dance Revolution，是二十幾年前曾經風靡全球的跳舞街機遊戲，時至今日，此遊戲雖然風光不如以往，"
        "但仍有許多忠實熱忱的玩家，也有一些把這個遊戲當成運動或拿來減肥的玩家。台北市內還有數個地方有這個機台，"
        "其中一台就藏身在東區裡面，請找到他並且在機台的前面拍合照！"
        "但請注意，大部分的玩家都不喜歡別人未經同意就拍照，所以你們必須等機台沒有人在遊玩的時候才能拍照，"
        "否則就先乖乖欣賞玩家的舞步吧！",
    ),
}

# name -> image_url. A reference photo shown alongside the challenge's public
# teaser (visible on the map before a team even starts it — see
# ChallengeTeaser in frontend/src/types.ts) — so it must show what to look
# for (a DDR cabinet, a character), never the actual venue/answer. Files live
# in frontend/public/challenge-images/ (see the README there) and are served
# at this exact path by the built SPA.
_IMAGES: dict[str, str] = {
    "忠孝敦化街機任務": "/challenge-images/ddr-machine.jpg",
    "西門動漫朝聖任務": "/challenge-images/kousaka-honoka.jpg",
    "美麗華摩天輪任務": "/challenge-images/miramar-stairs.jpg",
}

# Manual coordinate corrections, keyed by (map-visible) challenge name —
# takes priority over the lat/lng baked into _CHALLENGES below. Same idea as
# seed_stations.py's _COORD_OVERRIDES: generate entries with the superadmin
# "任務管理" tab's 任務座標 mode — pick a challenge, drag/click its marker to
# the right spot, then use its 輸出 button to get a properly-formatted entry
# to paste in here.
_COORD_OVERRIDES: dict[str, tuple[float, float]] = {}

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

    # --- Real, content-written challenges (see _CONTENT above) ---
    # ADMIN ONLY — never put this in _CONTENT's description, it must not
    # reach the team via the API. Current answer key is still a placeholder,
    # swap in the real 7 club names/answers before this goes active:
    #   社團A (有)  社團B (無)  社團C (無)  社團D (無)
    #   社團E (有)  社團F (有)  社團G (無)
    ("台大二活任務", "fixed", {"chips": 50}, "台大二活門口", 25.0184, 121.5388, "queued"),
    ("西門動漫朝聖任務", "fixed", {"chips": 80}, "西門站5號出口", 25.0424, 121.5077, "queued"),
    ("建成圓環任務", "variable", {"chips_per_unit": 1, "unit_label": "數字"}, "建成圓環", 25.0576, 121.5126, "queued"),
    ("台北地下街任務", "steal", {"steal_pct": 50}, "台北地下街Y1出口", 25.0526, 121.5203, "queued"),

    # ADMIN ONLY — correct shop is "ieat早午餐（真極品牛肉麵）". Coordinates are
    # nudged ~90m off the exact 葫洲站 point (25.072689, 121.607242) so the
    # challenge pin doesn't render on top of the station dot on the map;
    # refine with the superadmin 任務座標 tool once the shop's real spot is
    # confirmed on the ground.
    ("葫洲站早午餐任務", "fixed", {"chips": 30}, "葫洲站", 25.071989, 121.607842, "queued"),
    ("美麗華摩天輪任務", "variable", {"chips_per_unit": 50, "unit_label": "趟"}, "美麗華百樂園", 25.0833, 121.5828, "queued"),
    # ADMIN ONLY — correct arcade is "明曜百貨11樓卡通尼樂園". Coordinates are
    # nudged slightly off the exact 忠孝敦化站 point (25.041495, 121.549656)
    # for the same map-overlap reason as above.
    ("忠孝敦化街機任務", "fixed", {"chips": 40}, "忠孝敦化站", 25.042195, 121.550256, "queued"),
]


async def seed(conn) -> None:
    """Idempotent upsert by `name`. `pool_state` is intentionally absent from
    the ON CONFLICT SET clause — only set on first INSERT — so redeploying
    mid-event never resets a challenge that's already gone active/retired.

    `name` is the map-visible title (location-flavored only, e.g. "饒河街任務")
    — `inner_title` is the real/flavor title, hidden alongside `description`
    until a team's attempt is approved to start."""
    for name, ctype, reward_config, location_name, lat, lng, initial_state in _CHALLENGES:
        inner_title, description = _CONTENT.get(name, (TBD, TBD))
        lat, lng = _COORD_OVERRIDES.get(name, (lat, lng))
        image_url = _IMAGES.get(name)
        await conn.execute(
            """INSERT INTO challenges (name, inner_title, description, type, reward_config, location_name, lat, lng, image_url, pool_state)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
               ON CONFLICT (name) DO UPDATE
               SET inner_title = EXCLUDED.inner_title, description = EXCLUDED.description, type = EXCLUDED.type,
                   reward_config = EXCLUDED.reward_config, location_name = EXCLUDED.location_name,
                   lat = EXCLUDED.lat, lng = EXCLUDED.lng, image_url = EXCLUDED.image_url""",
            name, inner_title, description, ctype, json.dumps(reward_config), location_name, lat, lng, image_url, initial_state,
        )
