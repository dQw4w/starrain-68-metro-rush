"""Seeds the real Taipei Metro (TRTC) network: 6 main lines, 3 branches, ~131 stations.

Coordinates for stations come from a real GIS source (leoluyi/taipei_mrt,
itself derived from TRTC open data). The Circular Line (環狀線) and
branch line definitions have been updated for correct rendering and topology.

`seed()` is a full idempotent upsert and runs automatically on every backend
startup (see migrate.py) — editing anything in this file (stations, lines,
_LINE_WAYPOINTS, ...) and redeploying is enough, there is no separate DB step.
Can also be run standalone with `python seed_stations.py`.
"""
import asyncio

from loguru import logger

LINES = [
    # code, name_zh,      name_en,              color_hex, sort_order
    ("R",    "淡水信義線", "Tamsui-Xinyi Line",     "#E3002C", 1),
    ("R_BR", "新北投支線", "Xinbeitou Branch",      "#FD92A3", 2),
    ("BL",   "板南線",     "Bannan Line",           "#0070BD", 3),
    ("BR",   "文湖線",     "Wenhu Line",            "#C48C31", 4),
    ("O",    "中和新蘆線", "Zhonghe-Xinlu Line",    "#F8B61C", 5),
    ("O_BR", "蘆洲支線",   "Luzhou Branch",         "#F8B61C", 6),
    ("G",    "松山新店線", "Songshan-Xindian Line", "#008659", 7),
    ("G_BR", "小碧潭支線", "Xiaobitan Branch",      "#CEE779", 8),
    ("Y",    "環狀線",     "Circular Line",         "#FFD100", 9),
]

# Real coordinates (lat, lng) from GIS open data, keyed by station name.
_REAL_COORDS: dict[str, tuple[float, float]] = {
    "七張": (24.975083, 121.542911), "三和國中": (25.076808, 121.486347),
    "三民高中": (25.085670, 121.473241), "三重": (25.055599, 121.483947),
    "三重國小": (25.069935, 121.497441), "中山": (25.052676, 121.520397),
    "中山國中": (25.060806, 121.544216), "中山國小": (25.062651, 121.527664),
    "中正紀念堂": (25.034274, 121.517049), "丹鳳": (25.028921, 121.422699),
    "亞東醫院": (24.998589, 121.452649), "信義安和": (25.033150, 121.553233),
    "先嗇宮": (25.046527, 121.472123), "內湖": (25.083506, 121.594206),
    "公館": (25.014707, 121.534347), "六張犁": (25.023845, 121.553058),
    "劍南路": (25.084898, 121.555607), "劍潭": (25.084236, 121.524969),
    "動物園": (24.998277, 121.579325), "北投": (25.131907, 121.498591),
    "北門": (25.049294, 121.510279), "南京三民": (25.051436, 121.564397),
    "南京復興": (25.051870, 121.543577), "南勢角": (24.990409, 121.509173),
    "南港": (25.052178, 121.607634), "南港展覽館": (25.054566, 121.617622),
    "南港軟體園區": (25.059899, 121.615954), "古亭": (25.026886, 121.522568),
    "台北101/世貿": (25.032979, 121.563490), "台北小巨蛋": (25.051647, 121.552003),
    "台北橋": (25.062944, 121.499868), "台北車站": (25.046233, 121.517438),
    "台電大樓": (25.020693, 121.528187), "唭哩岸": (25.120858, 121.506265),
    "善導寺": (25.044813, 121.523340), "國父紀念館": (25.041347, 121.557689),
    "圓山": (25.071380, 121.520132), "土城": (24.973226, 121.444452),
    "士林": (25.093474, 121.526192), "大坪林": (24.982914, 121.541366),
    "大安": (25.032821, 121.543626), "大安森林公園": (25.033535, 121.535308),
    "大橋頭": (25.062922, 121.512849), "大湖公園": (25.083809, 121.602313),
    "大直": (25.080477, 121.548149), "奇岩": (25.125585, 121.501083),
    "小南門": (25.035673, 121.510782), "小碧潭": (24.973415, 121.530058),
    "市政府": (25.041179, 121.565259), "府中": (25.008935, 121.459219),
    "後山埤": (25.044279, 121.582004), "徐匯中學": (25.080742, 121.479616),
    "復興崗": (25.137447, 121.485208), "忠孝復興": (25.041602, 121.543794),
    "忠孝敦化": (25.041495, 121.549656), "忠孝新生": (25.042355, 121.532919),
    "忠義": (25.130751, 121.473122), "文德": (25.078533, 121.584969),
    "新北投": (25.136936, 121.502531), "新埔": (25.022996, 121.467987),
    "新店": (24.957872, 121.537610), "新店區公所": (24.967394, 121.541299),
    "新莊": (25.036148, 121.452318), "昆陽": (25.050189, 121.593020),
    "明德": (25.109794, 121.518820), "景安": (24.993922, 121.505091),
    "景美": (24.993178, 121.540921), "木柵": (24.998253, 121.573176),
    "東湖": (25.067578, 121.611737), "東門": (25.033928, 121.528322),
    "松山": (25.050002, 121.577733), "松山機場": (25.063104, 121.551635),
    "松江南京": (25.052025, 121.533049), "板橋": (25.014297, 121.462882),
    "民權西路": (25.062877, 121.519363), "永安市場": (25.002556, 121.511125),
    "永寧": (24.967221, 121.436827), "永春": (25.040864, 121.575873),
    "江子翠": (25.029905, 121.472237), "海山": (24.985548, 121.448875),
    "淡水": (25.167993, 121.445258), "港墘": (25.079995, 121.575283),
    "石牌": (25.114420, 121.515642), "科技大樓": (25.025992, 121.543451),
    "竹圍": (25.136949, 121.459456), "紅樹林": (25.154114, 121.458955),
    "台大醫院": (25.041827, 121.516220), "芝山": (25.102811, 121.522542),
    "菜寮": (25.059648, 121.491138), "萬芳社區": (24.998608, 121.568067),
    "萬芳醫院": (24.999504, 121.558029), "萬隆": (25.001965, 121.539002),
    "葫洲": (25.072689, 121.607242), "蘆洲": (25.091564, 121.464357),
    "行天宮": (25.057966, 121.533156), "西湖": (25.082161, 121.567212),
    "西門": (25.042213, 121.508488), "象山": (25.032793, 121.570666),
    "輔大": (25.032769, 121.435812), "辛亥": (25.005384, 121.557010),
    "迴龍": (25.022517, 121.412663), "關渡": (25.125785, 121.467200),
    "雙連": (25.057647, 121.520710), "頂埔": (24.959433, 121.418882),
    "頂溪": (25.013619, 121.515450), "頭前庄": (25.039607, 121.461625),
    "麟光": (25.018523, 121.558827), "龍山寺": (25.035229, 121.501221),
}

# Circular Line (Y) — Corrected coordinates
_Y_LINE_COORDS: dict[str, tuple[float, float]] = {
    "十四張": (24.982260, 121.528430), "秀朗橋": (24.991823, 121.523555),
    "景平": (24.993437, 121.516560), "中和": (25.002220, 121.499044),
    "橋和": (25.004739, 121.490799), "中原": (25.007629, 121.484218),
    "板新": (25.013532, 121.471676), "新埔民生": (25.026125, 121.466848),
    "幸福": (25.048702, 121.459145), "新北產業園區": (25.061556, 121.459888),
}

# Manual corrections take priority over both dicts above, so you don't have to
# go hunt down which one a station's original entry lives in — just paste
# corrected coordinates here. Generate these with the super-admin "路線編輯"
# tool's 車站座標 mode: pick a station, drag/click its marker to the right
# spot, then use its 輸出 button to get a properly-formatted entry to paste.
_COORD_OVERRIDES: dict[str, tuple[float, float]] = {
    "南京復興": (25.051839, 121.544055),
    "大安": (25.033360, 121.543615),
}

_COORDS = {**_REAL_COORDS, **_Y_LINE_COORDS, **_COORD_OVERRIDES}

# Per-line ordered station name lists (order only drives the drawn polyline).
_LINE_STATIONS: dict[str, list[str]] = {
    "R": [
        "淡水", "紅樹林", "竹圍", "關渡", "忠義", "復興崗", "北投", "奇岩", "唭哩岸",
        "石牌", "明德", "芝山", "士林", "劍潭", "圓山", "民權西路", "雙連", "中山",
        "台北車站", "台大醫院", "中正紀念堂", "東門", "大安森林公園", "大安",
        "信義安和", "台北101/世貿", "象山",
    ],
    "R_BR": [
        "北投", "新北投",
    ],
    "BL": [
        "頂埔", "永寧", "土城", "海山", "亞東醫院", "府中", "板橋", "新埔", "江子翠",
        "龍山寺", "西門", "台北車站", "善導寺", "忠孝新生", "忠孝復興", "忠孝敦化",
        "國父紀念館", "市政府", "永春", "後山埤", "昆陽", "南港", "南港展覽館",
    ],
    "BR": [
        "動物園", "木柵", "萬芳社區", "萬芳醫院", "辛亥", "麟光", "六張犁", "科技大樓",
        "大安", "忠孝復興", "南京復興", "中山國中", "松山機場", "大直", "劍南路",
        "西湖", "港墘", "文德", "內湖", "大湖公園", "葫洲", "東湖", "南港軟體園區",
        "南港展覽館",
    ],
    "O": [
        "南勢角", "景安", "永安市場", "頂溪", "古亭", "東門", "忠孝新生", "松江南京",
        "行天宮", "中山國小", "民權西路", "大橋頭", "台北橋", "菜寮", "三重", "先嗇宮",
        "頭前庄", "新莊", "輔大", "丹鳳", "迴龍",
    ],
    "O_BR": [
        "大橋頭", "三重國小", "三和國中", "徐匯中學", "三民高中", "蘆洲",
    ],
    "G": [
        "新店", "新店區公所", "七張", "大坪林", "景美", "萬隆", "公館", "台電大樓", "古亭",
        "中正紀念堂", "小南門", "西門", "北門", "中山", "松江南京", "南京復興", "台北小巨蛋",
        "南京三民", "松山",
    ],
    "G_BR": [
        "七張", "小碧潭",
    ],
    "Y": [
        "大坪林", "十四張", "秀朗橋", "景平", "景安", "中和", "橋和", "中原", "板新",
        "板橋", "新埔民生", "頭前庄", "幸福", "新北產業園區",
    ],
}

# Invisible "shape points" inserted between two consecutive stations on a line,
# so the drawn polyline follows the real track curve instead of a straight
# line between station dots. Purely cosmetic — not real stations, not
# clickable, no gameplay effect. Key is (line_code, from_station, to_station)
# using the exact names/order from _LINE_STATIONS above (from earlier in the
# list to later); value is an ordered list of (lat, lng) points to insert
# between them.
#
# Generate these with the super-admin "路線編輯" (line waypoint editor) tool —
# pick an adjacent station pair, click along the real curve on the map, then
# use its 輸出 button to get properly-formatted entries to paste in here.
# (Previously hand-guessed entries lived here and were inaccurate — removed.)
_LINE_WAYPOINTS: dict[tuple[str, str, str], list[tuple[float, float]]] = {
    ("BR", "動物園", "木柵"): [(24.997587, 121.578285), (24.997446, 121.577936), (24.997373, 121.577534), (24.997397, 121.577083)],
    ("BR", "木柵", "萬芳社區"): [(24.998646, 121.570984), (24.998666, 121.570732), (24.998676, 121.570576)],
    ("BR", "萬芳社區", "萬芳醫院"): [(24.998549, 121.567052), (24.998525, 121.566773), (24.997942, 121.564032), (24.997719, 121.563474), (24.997408, 121.562691), (24.997204, 121.562251), (24.997077, 121.561575), (24.997126, 121.560996), (24.997194, 121.560352), (24.997272, 121.560009), (24.997447, 121.559719), (24.997743, 121.559424), (24.998258, 121.559156), (24.998836, 121.558903), (24.999055, 121.558694)],
    ("BR", "萬芳醫院", "辛亥"): [(24.999859, 121.557434), (25.000257, 121.557165), (25.001667, 121.556758), (25.001924, 121.556747), (25.002147, 121.556833), (25.002464, 121.557069), (25.002798, 121.557262), (25.003085, 121.557299), (25.003358, 121.557283), (25.004748, 121.556790), (25.004864, 121.556758)],
    ("BR", "辛亥", "麟光"): [(25.005945, 121.557337), (25.006226, 121.557659), (25.006542, 121.558008), (25.006780, 121.558292), (25.007747, 121.559005), (25.008803, 121.559837), (25.009279, 121.560084), (25.009969, 121.560298), (25.016250, 121.560373), (25.016648, 121.560363), (25.017018, 121.560255), (25.017280, 121.560051)],
    ("BR", "六張犁", "科技大樓"): [(25.024155, 121.552756), (25.024320, 121.552541), (25.024378, 121.552252), (25.024825, 121.543840), (25.024864, 121.543658), (25.025020, 121.543475)],
    
}


async def seed(conn) -> None:
    """Fully idempotent upsert — safe (and intended) to run on every startup,
    so editing the data above and redeploying is enough; no manual DB step
    needed. Stations/lines are matched by name/code and their lat/lng/color/
    sequence are updated in place. Stations removed from the data below are
    NOT deleted (to avoid ever dropping a station that already has a live
    claim/log history) — only their line associations are pruned so a
    station moved between lines doesn't keep a stale line membership.
    """
    line_ids: dict[str, int] = {}
    for code, name_zh, name_en, color_hex, sort_order in LINES:
        row = await conn.fetchrow(
            """INSERT INTO lines (code, name_zh, name_en, color_hex, sort_order)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (code) DO UPDATE
               SET name_zh = EXCLUDED.name_zh, name_en = EXCLUDED.name_en,
                   color_hex = EXCLUDED.color_hex, sort_order = EXCLUDED.sort_order
               RETURNING id""",
            code, name_zh, name_en, color_hex, sort_order,
        )
        line_ids[code] = row["id"]

    # Sequence numbers are spaced out (100, 200, 300, ...) instead of packed
    # (1, 2, 3, ...) so line_waypoints can be inserted between any two
    # consecutive stations without renumbering anything.
    SEQ_STEP = 100

    station_ids: dict[str, int] = {}
    station_line_pairs: set[tuple[int, int]] = set()
    for code, names in _LINE_STATIONS.items():
        for i, name in enumerate(names):
            seq = (i + 1) * SEQ_STEP
            if name not in station_ids:
                lat, lng = _COORDS[name]
                row = await conn.fetchrow(
                    """INSERT INTO stations (name_zh, name_en, lat, lng) VALUES ($1, $1, $2, $3)
                       ON CONFLICT (name_zh) DO UPDATE SET lat = EXCLUDED.lat, lng = EXCLUDED.lng
                       RETURNING id""",
                    name, lat, lng,
                )
                station_ids[name] = row["id"]
                await conn.execute(
                    "INSERT INTO station_claims (station_id, value) VALUES ($1, 0) ON CONFLICT DO NOTHING",
                    row["id"],
                )
            await conn.execute(
                """INSERT INTO station_lines (station_id, line_id, sequence)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (station_id, line_id) DO UPDATE SET sequence = EXCLUDED.sequence""",
                station_ids[name], line_ids[code], seq,
            )
            station_line_pairs.add((station_ids[name], line_ids[code]))

    # Prune line memberships that are no longer in the data (e.g. a station
    # moved to a different line), without touching the station rows themselves.
    station_id_list = list(station_ids.values())
    if station_id_list:
        current_pairs = await conn.fetch(
            "SELECT station_id, line_id FROM station_lines WHERE station_id = ANY($1::int[])",
            station_id_list,
        )
        stale = [
            (r["station_id"], r["line_id"])
            for r in current_pairs
            if (r["station_id"], r["line_id"]) not in station_line_pairs
        ]
        for station_id, line_id in stale:
            await conn.execute(
                "DELETE FROM station_lines WHERE station_id = $1 AND line_id = $2", station_id, line_id
            )

    # Waypoints have no identity of their own to upsert against, so each
    # affected line's waypoints are simply wiped and rewritten from scratch.
    seeded_line_ids = list(line_ids.values())
    if seeded_line_ids:
        await conn.execute("DELETE FROM line_waypoints WHERE line_id = ANY($1::int[])", seeded_line_ids)
    for code, names in _LINE_STATIONS.items():
        for i in range(len(names) - 1):
            from_name, to_name = names[i], names[i + 1]
            points = _LINE_WAYPOINTS.get((code, from_name, to_name))
            if not points:
                continue
            from_seq = (i + 1) * SEQ_STEP
            to_seq = (i + 2) * SEQ_STEP
            step = (to_seq - from_seq) / (len(points) + 1)
            for j, (lat, lng) in enumerate(points, start=1):
                await conn.execute(
                    "INSERT INTO line_waypoints (line_id, sequence, lat, lng) VALUES ($1, $2, $3, $4)",
                    line_ids[code], round(from_seq + step * j), lat, lng,
                )

    waypoint_count = sum(len(v) for v in _LINE_WAYPOINTS.values())
    logger.info(f"Seeded {len(line_ids)} lines, {len(station_ids)} stations, {waypoint_count} line waypoints.")


if __name__ == "__main__":
    import asyncpg
    from config import DATABASE_URL

    async def main():
        conn = await asyncpg.connect(DATABASE_URL)
        async with conn.transaction():
            await seed(conn)
        await conn.close()

    asyncio.run(main())