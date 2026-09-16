"""Seeds this event's real, fully-written challenges (see _CONTENT below for
each one's actual title/task text). This file used to also seed ~36
placeholder landmark challenges with a literal "TBD" description — those
have been removed entirely (see the DELETE at the end of seed(), which drops
any challenge no longer listed in _CHALLENGES rather than just hiding it).

Every challenge's `description` defaults to a literal "TBD" placeholder if
it isn't in _CONTENT, so a new entry here is still playable as soon as its
reward/location are filled in, even before real content is written.
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
        "限時10分鐘，請上去二活的8-10樓，去看二活的8-10樓有哪些各社辦，可以分工合作分頭行動。"
        "結束後回到此地（二活一樓門口），隨隊管理員將會講出7個社團的名字，你們要告訴他二活是否存在該社團的社辦。"
        "回答時請選一個人做為代表，其他人可以在旁邊幫忙討論，並且告訴他答案。"
        "回答時禁止看手機或是筆記。",
    ),
    "西門町任務": (
        "西門町任務：致二次元裡獨特的你",
        "高松燈（來自 BanG Dream! It's MyGO!!!!!）與天王寺璃奈"
        "（來自《LoveLive! 虹咲學園校園偶像同好會》）都是常被觀眾認為帶有自閉症特質的角色："
        "前者在語言表達上有困難，且有著特殊的執著與愛好（例如收集石頭）；"
        "後者則難以透過臉部展現情緒，因此她會用手繪的表情板告訴大家自己現在的心情，"
        "也曾面臨孤獨、難以交到朋友的處境。"
        "西門町是二次元動漫文化的聖地，請找到「高松燈」或「天王寺璃奈」任一位角色的周邊，"
        "價格300元（含）以內，把它買下來"
        "（活動結束後請把周邊轉交給主辦人，主辦人會給你錢）。"
        "周邊可為同人或是官方商品，但周邊上不得出現其他角色的圖案。",
    ),
    "仁愛圓環任務": (
        "許願圓環：喊出你的極限數字",
        "恭喜你們來到了台北市最具代表性且還沒有被拆掉的圓環之一，仁愛圓環。"
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
    "葫洲站任務": (
        "巷口的牛肉麵回憶",
        "主辦人的家就在葫洲站附近。雖然主辦人總是笑稱內湖是美食沙漠，但這裡也還是有很多從小吃到大的好滋味。"
        "請在附近找到一間有賣牛肉麵的平價台式早午餐店，並在店家前面拍合照！"
        "只有一次機會，如果找錯家就算任務失敗。",
    ),
    "美麗華任務": (
        "陪你爬上摩天輪的路",
        "歡迎來到美麗華，這裡有著台灣最美的摩天輪之一。但主辦人同樣也很喜歡美麗華室外的樓梯，"
        "且從地面層沿著樓梯爬到最上面就能抵達摩天輪的所在處！所以，主辦人想讓你們親自體驗爬這座樓梯的感覺。"
        "請大家在樓梯的地面層處預備、限時10分鐘，事先決定好要爬幾趟。一趟為一上一下，"
        "需抵達摩天輪所在的樓層才能折返，且所有組員都必須同步完成。"
        "如果在時間內達成你們指定的趟數，則可獲得代幣，若無法，即使只是差1秒或有1個人差了1格樓梯，任務失敗。",
    ),
    "忠孝敦化任務": (
        "東區裡的舞步傳說",
        "如圖，Dance Dance Revolution，是二十幾年前曾經風靡全球的跳舞街機遊戲，時至今日，此遊戲雖然風光不如以往，"
        "但仍有許多忠實熱忱的玩家，也有一些把這個遊戲當成運動或拿來減肥的玩家。台北市內還有數個地方有這個機台，"
        "其中一台就藏身在東區裡面，請找到他並且在機台的前面拍合照！"
        "但請注意，大部分的玩家都不喜歡別人未經同意就拍照，所以你們必須等機台沒有人在遊玩的時候才能拍照，"
        "否則就先乖乖欣賞玩家的舞步吧！",
    ),
}

# name -> admin_notes. The answer key / judging reference for whoever
# approves that challenge's challenge_result request (a team admin, or the
# super admin acting as backup approver) — rendered right on the approval
# card (see routers/admin.py's /challenges and TeamAdminPage.tsx). Never
# reaches a team: absent from ChallengeTeaser and from the team-scoped
# detail endpoint (see models.py's ChallengeAdminView docstring).
_ADMIN_NOTES: dict[str, str] = {
    "台大二活任務": (
        "請告訴大家幾點幾分要回到樓下集合，如果超時5分鐘有人還沒回來就算是任務失敗"
        "社團是否存在二活，逐一詢問時對照：\n自閉星雨服務團(有，10F，答錯你就可以退社了)\n 卡通漫畫研究社(無，社辦在一活)\n"
        "臺灣韓國學生交流會(無，只有臺灣日本學生交流會)\n 熱音社(無，只有椰風搖滾)\n"
        "綺巧手工藝社(有，9F)\n 日本麻雀研究社(有)\n 登山社(無，社辦在一活)\n"
    ),
    "仁愛圓環任務": (
        "確認是否在正確的圓環。隊伍喊出的目標數字須介於30~100之間；"
        "* 代表該數字是6的倍數、8的倍數，或數字中包含6或8，該次應該拍手而不是喊數字，"
        "只要對照到隊伍指定的目標數字那一格即可，不必整份都看：\n"
        "1 2 3 4 5 * 7 * 9 10\n"
        "11 * 13 14 15 * 17 * 19 20\n"
        "21 22 23 * 25 * 27 * 29 *\n"
        "31 * 33 34 35 * 37 * 39 *\n"
        "41 * 43 44 45 * 47 * 49 50\n"
        "51 52 53 * 55 * 57 * 59 *\n"
        "* * * * * * * * * 70\n"
        "71 * 73 74 75 * 77 * 79 *\n"
        "* * * * * * * * * *\n"
        "91 92 93 94 95 * 97 * 99 100"
    ),
    "西門町任務": (
        "接受「高松燈」或「天王寺璃奈」任一位角色的周邊，兩者皆可判成功；"
        "確認：商品上沒有其他角色圖案、價格在300元（含）以內。"
    ),
    "葫洲站任務": "正確店家：ieat早午餐（真極品牛肉麵）。找錯家直接判失敗，只有一次機會。",
    "忠孝敦化任務": "正確地點：明曜百貨11樓卡通尼樂園。務必確認機台當下無人在玩，合照才算數。",
    "台北地下街任務": "正確答案：825公尺。誤差在100公尺（含）以內都算成功。",
}

# name -> image_url. A reference photo shown alongside the task description —
# hidden until a team's attempt is approved to start, same as description
# itself (see ChallengeTeaser vs. Challenge in models.py) — so it must show
# what to look for (a DDR cabinet, a character), never the actual
# venue/answer. Files live in frontend/public/challenge-images/ (see the
# README there) and are served at this exact path by the built SPA.
_IMAGES: dict[str, str] = {
    "忠孝敦化任務": "/challenge-images/ddr-machine.png",
    "西門町任務": "/challenge-images/takamatsu-tomori.png",
    "美麗華任務": "/challenge-images/miramar-stairs.png",
}

# name -> second reference photo (optional). Only 西門町任務 uses this
# right now — the task accepts merch of either of two characters, so both
# get shown. See models.py's Challenge.image_url_2 docstring.
_IMAGES_2: dict[str, str] = {
    "西門町任務": "/challenge-images/tennoji-rina.png",
}

# Manual coordinate corrections, keyed by (map-visible) challenge name —
# takes priority over the lat/lng baked into _CHALLENGES below. Same idea as
# seed_stations.py's _COORD_OVERRIDES: generate entries with the superadmin
# "任務管理" tab's 任務座標 mode — pick a challenge, drag/click its marker to
# the right spot, then use its 輸出 button to get a properly-formatted entry
# to paste in here.
_COORD_OVERRIDES: dict[str, tuple[float, float]] = {}

# name, type, reward_config, location_name, lat, lng, initial_pool_state
#
# Placeholder landmark challenges (36 of them, TBD reward-only entries) have
# been removed — every challenge here now has real, written content. The 3
# "active" ones below (all type='fixed') preserve the game's opening-pool
# rule (exactly 3 start active, so the map isn't empty before a superadmin
# ever touches anything); the rest start 'queued' and enter play later via
# activate_initial_pool()/_refill_pool() in game_logic.py.
_CHALLENGES: list[tuple] = [
    ("台大二活任務", "multiplier", {"multiplier_pct": 40}, "台大二活門口", 25.012938045228722, 121.53662176506363, "queued"),
    ("西門町任務", "fixed", {"chips": 80}, "西門站5號出口", 25.04286, 121.5088, "active"),
    ("仁愛圓環任務", "variable", {"chips_per_unit": 1, "unit_label": "數字"}, "仁愛圓環", 25.037778, 121.548889, "queued"),
    ("台北地下街任務", "steal", {"steal_pct": 50}, "台北地下街Y1出口", 25.04886, 121.51906, "queued"),

    ("葫洲站任務", "fixed", {"chips": 30}, "葫洲站", 25.072610389433837, 121.60702478470597, "active"),
    ("美麗華任務", "variable", {"chips_per_unit": 50, "unit_label": "趟"}, "美麗華百樂園", 25.083694238417248, 121.557050674598, "queued"),
    ("忠孝敦化任務", "fixed", {"chips": 40}, "忠孝敦化站", 25.041351036032598, 121.55073436774637, "active"),
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
        image_url_2 = _IMAGES_2.get(name)
        admin_notes = _ADMIN_NOTES.get(name, "")
        await conn.execute(
            """INSERT INTO challenges (name, inner_title, description, type, reward_config, location_name, lat, lng, image_url, image_url_2, admin_notes, pool_state)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
               ON CONFLICT (name) DO UPDATE
               SET inner_title = EXCLUDED.inner_title, description = EXCLUDED.description, type = EXCLUDED.type,
                   reward_config = EXCLUDED.reward_config, location_name = EXCLUDED.location_name,
                   lat = EXCLUDED.lat, lng = EXCLUDED.lng, image_url = EXCLUDED.image_url,
                   image_url_2 = EXCLUDED.image_url_2, admin_notes = EXCLUDED.admin_notes""",
            name, inner_title, description, ctype, json.dumps(reward_config), location_name, lat, lng, image_url,
            image_url_2, admin_notes, initial_state,
        )

    # Anything in the DB that's no longer listed above (e.g. the placeholder
    # landmark challenges this file used to seed) is actually deleted, not
    # just retired — schema.sql points every table that can reference a
    # challenge (challenge_attempts, approval_requests, action_log) at it
    # with either ON DELETE CASCADE or SET NULL, so this can't fail on a
    # dangling reference even if that placeholder was already attempted.
    seeded_names = [name for name, *_ in _CHALLENGES]
    await conn.execute(
        "DELETE FROM challenges WHERE NOT (name = ANY($1::text[]))",
        seeded_names,
    )
