"""The decision makers.

`LLMAgent` hands the local model the current game state plus a numbered list
of legal options and takes back a number. `HeuristicAgent` plays a plain
greedy game with no model at all — useful as a baseline, as a sanity check
that the engine itself is sane, and as the fallback whenever the model
returns something unparseable.
"""
from __future__ import annotations

import random

from engine import ClaimOffer, Decision, Engine, Option, TeamState
from llm import LLMClient, LLMError, extract_json
from network import haversine_m

SYSTEM_PROMPT = """你是一個捷運大富翁類遊戲的玩家，正在指揮一支小隊。

## 怎麼算贏
1. 第一順位：遊戲結束時「擁有的車站數」最多。
2. 第二順位（只有車站數相同時才比）：手上剩的代幣。

所以**代幣只是用來換車站的工具，留在手上沒有意義**。遊戲結束時還抱著一堆代幣
卻沒幾座站，就是輸。

## 代幣只出不進 —— 這是你最容易忽略的事
佔領車站會把代幣花掉，而且**遊戲裡唯一能把代幣賺回來的方式就是解任務**。
你一開始的代幣撐不了整場：用完之後你就再也不能佔任何站，只能乾等到結束。

所以不要把任務當成「有空再說的加分題」，它是你的補給線。
看到標了 ★ 的任務選項（代表你正站在它最近的下車點），**優先考慮下車去做**，
錯過就得繞回來，很浪費時間。

## 最重要的三件事
1. **一直往沒去過的方向移動，沿路把沒人佔的站吃下來。** 無人佔領的站只要 1 枚就
   能拿下，這是最划算的得分方式。看到標記 ✅ 的站就該下車佔領。
2. **站在自己的車站上「防守」是沒有用的，這遊戲沒有防守這個動作。** 你人在不在
   那裡完全不影響對手能不能搶走它。回到自己已經佔滿（標記 ❌）的站是純粹浪費時間。
   同理，**開局不要急著加碼**，那是把本來可以拿去佔新站的代幣鎖死。
3. **時間是唯一真正稀缺的資源。** 每次搭車 2~6 分鐘，整場只有 360 分鐘。
   在同幾站之間來回是最糟糕的打法。

## 其他規則
- 加碼只是把站養高，讓對手要花更多代幣才搶得走；它**不會增加你的車站數**，
  而且一旦養到上限就再也不能加了。開局不必急著把站養滿，先去多吃幾個站。
- 搶對手的站：要花「站上代幣數 +1」枚。站數差距大的時候值得考慮。
- 任務可以賺代幣（有些還能直接偷對手的代幣或翻倍），但要花時間走過去，而且會失敗。
  代幣不夠用來佔站的時候，就該去做任務。
- 如果附近沒有任務可選，表示任務都在遠處——看「任務分布」那一段，搭車往那邊靠近。

## 常見錯誤（不要犯）
- ❌ 在兩三個站之間來回走動卻什麼都沒做
- ❌ 回到自己已經佔滿的站
- ❌ 看到前面幾站都是自己的就覺得無路可走——看每個方向的「→」提示，
     它會告訴你再往前幾站有無人站或對手的站
- ❌ 把代幣存著不花

## 你每一回合要同時做兩個決定
**佔領不花時間**，是在月台上等車時順手完成的，所以它跟移動是同時進行的，
你要在同一個回覆裡一起決定：

1. `claim`：要在腳下這一站投入幾枚代幣（0 = 不投）。沒有「可佔領」那段就填 0。
2. `move`：接下來怎麼移動（從下面的移動選項挑一個編號）。

典型的好回合是「佔領這站 + 繼續往前搭車」，兩件事一起做。

## 回覆格式
只輸出 JSON，不要有其他文字：
{"claim": <投入代幣數，0 表示不佔領>, "move": <移動選項編號>, "call": <喊出的數量，只有 call your shot 任務需要>, "notes": "<接下來幾步的計畫>"}

notes 請寫**接下來要做什麼的計畫**，不要只是複述剛剛做了什麼。"""


def _runway_line(engine: Engine, team: TeamState) -> str:
    """Spell out how much game the team has left in the bank. Chips only ever
    go down outside of challenges, and the agent otherwise never notices it's
    about to be unable to do anything at all."""
    free = [s for s, c in engine.claims.items() if c.owner is None]
    # An unclaimed station costs 1; that's the cheapest thing chips buy.
    if team.chips <= 0:
        return "⚠️ 你已經沒有代幣了，除非去解任務賺回來，否則你接下來什麼都做不了。"
    warn = ""
    if team.chips <= 10:
        warn = "　⚠️ 代幣快用完了，該去解任務補充了！"
    return (f"代幣存量：還能佔下約 {team.chips} 座無人站"
            f"（全場目前還有 {len(free)} 座無人站）{warn}")


def _state_block(engine: Engine, team: TeamState) -> str:
    me = team
    others = [t for t in engine.teams.values() if t.name != team.name]
    my_stations = engine.stations_owned(me.name)
    lines = [
        f"遊戲時間：第 {engine.minute} 分鐘 / 共 {engine.cfg.game_minutes} 分鐘"
        f"（剩 {engine.cfg.game_minutes - engine.minute} 分鐘）",
        f"你是：{me.name}",
        f"【你的車站數：{my_stations}】（這是勝負關鍵）｜你的代幣：{me.chips} 枚",
        _runway_line(engine, me),
    ]
    for o in others:
        o_st = engine.stations_owned(o.name)
        diff = my_stations - o_st
        trend = "你領先" if diff > 0 else ("平手" if diff == 0 else f"你落後 {-diff} 站")
        lines.append(f"對手 {o.name}：【{o_st} 站】｜{o.chips} 枚　→ {trend}")
    lines.append(f"你現在位置：「{me.station}」" + ("（在車上，剛到站）" if me.mode == "riding" else "（在站內）"))

    mine = [s for s, c in engine.claims.items() if c.owner == me.name]
    if mine:
        lines.append("你擁有的車站：" + "、".join(
            f"{s}({engine.claims[s].value}/{engine.claims[s].cap})" for s in mine[:12]
        ) + (" …" if len(mine) > 12 else ""))

    if len(me.recent_stations) >= 3:
        recent = me.recent_stations[-6:]
        warn = ""
        if len(set(recent[-4:])) <= 2 and len(recent) >= 4:
            warn = "　⚠️ 你一直在同幾站之間來回，這是在浪費時間，換個方向去吃新的站！"
        lines.append("你最近經過的站：" + " → ".join(recent) + warn)

    # Where the challenges are, so a far-away one can still be aimed at.
    active = [c for c in engine.net.challenges
              if engine.challenge_state.get(c.name) == "active" and c.name not in me.attempted]
    if active:
        here = engine.net.coords[me.station]
        rows = []
        for ch in active:
            stn, walk = engine.net.nearest_station_to(ch)
            km = haversine_m(here, (ch.lat, ch.lng)) / 1000
            rows.append((km, f"「{ch.name}」在 {stn} 站附近（下車後走 {walk} 分），"
                             f"直線距離你 {km:.1f} 公里，{engine._describe_reward(ch)}"))
        rows.sort()
        lines.append("任務分布（共 %d 個）：" % len(active))
        lines.extend("  - " + r[1] for r in rows[:5])
    else:
        lines.append("目前沒有你還能挑戰的任務。")

    if me.notes:
        lines.append(f"你上一步寫下的計畫：{me.notes}")
    return "\n".join(lines)


def _claim_block(offer: ClaimOffer | None) -> str:
    if offer is None:
        return "可佔領：這一站現在沒有你能投入的空間，claim 請填 0。"
    return (f"可佔領：{offer.label}\n"
            f"　→ claim 填 {offer.lo}~{offer.hi} 之間的數字，或填 0 表示不投。（不花時間）")


def _options_block(options: list[Option]) -> str:
    out = []
    for i, o in enumerate(options):
        extra = ""
        if o.call_range:
            extra = f"（請用 call 指定喊出的數量，範圍 {o.call_range[0]}~{o.call_range[1]}）"
        out.append(f"{i}. {o.label}　[耗時 {o.minutes} 分鐘]{extra}")
    return "\n".join(out)


class HeuristicAgent:
    """Greedy baseline: take a cheap station if you can afford it, otherwise
    go do a nearby challenge, otherwise keep riding."""

    def __init__(self, rng: random.Random):
        self.rng = rng

    def decide(self, engine: Engine, team: TeamState, options: list[Option]) -> Decision:
        by_key: dict[str, list[tuple[int, Option]]] = {}
        for i, o in enumerate(options):
            by_key.setdefault(o.key, []).append((i, o))

        # Claiming is free in time, so always take a station nobody holds.
        claim_amount = 0
        offer = engine.claim_offer(team)
        if offer is not None and offer.kind == "claim" and engine.claims[team.station].owner is None:
            claim_amount = offer.lo

        def d(i, **kw):
            return Decision(i, claim_amount=claim_amount, **kw)

        walks = sorted(by_key.get("walk", []), key=lambda t: t[1].minutes)
        if walks and walks[0][1].minutes <= 10:
            i, o = walks[0]
            call = None
            if o.call_range:
                lo, hi = o.call_range
                call = lo + (hi - lo) // 4          # conservative call
            return d(i, call_value=call, notes="greedy: nearby challenge")

        if "stay_on" in by_key:
            return d(by_key["stay_on"][0][0], notes="greedy: ride on")
        boards = by_key.get("board", [])
        if boards:
            return d(self.rng.choice(boards)[0], notes="greedy: board something")
        return d(len(options) - 1, notes="greedy: wait")


class LLMAgent:
    def __init__(self, client: LLMClient, fallback: HeuristicAgent, max_calls: int = 0):
        self.client = client
        self.fallback = fallback
        self.max_calls = max_calls

    def decide(self, engine: Engine, team: TeamState, options: list[Option]) -> Decision:
        if self.max_calls and team.llm_calls >= self.max_calls:
            return self.fallback.decide(engine, team, options)

        offer = engine.claim_offer(team)
        prompt = (f"{_state_block(engine, team)}\n\n{_claim_block(offer)}\n\n"
                  f"移動選項：\n{_options_block(options)}\n\n"
                  f"請同時決定 claim 和 move，回覆 JSON。")
        try:
            raw = self.client.chat(SYSTEM_PROMPT, prompt)
        except LLMError as e:
            print(f"  ! LLM error, falling back to heuristic: {e}")
            return self.fallback.decide(engine, team, options)
        team.llm_calls += 1
        if self.client.cfg.verbose:
            print(f"\n--- {team.name} @ {engine.minute}m ---\n{prompt}\n--> {raw.strip()[:400]}")

        parsed = extract_json(raw)
        if parsed is None or "move" not in parsed:
            return self.fallback.decide(engine, team, options)

        try:
            idx = int(parsed["move"])
        except (TypeError, ValueError):
            return self.fallback.decide(engine, team, options)
        if not 0 <= idx < len(options):
            return self.fallback.decide(engine, team, options)

        claim_amount = 0
        if offer is not None:
            try:
                raw_claim = int(parsed.get("claim", 0) or 0)
            except (TypeError, ValueError):
                raw_claim = 0
            # Anything positive is a genuine intent to claim; clamp it to the
            # legal band rather than throwing the turn away over a bad number.
            if raw_claim > 0:
                claim_amount = max(offer.lo, min(offer.hi, raw_claim))

        opt = options[idx]
        call = None
        if opt.call_range:
            lo, hi = opt.call_range
            try:
                call = max(lo, min(hi, int(parsed.get("call", lo))))
            except (TypeError, ValueError):
                call = lo
        notes = str(parsed.get("notes", ""))[:400]
        return Decision(idx, claim_amount=claim_amount, call_value=call, notes=notes)


class ExplorerAgent:
    """A purposeful no-LLM baseline: always claim what's free, take a
    challenge when you're standing at its drop-off, and otherwise head
    toward the nearest station you don't own.

    Exists because the greedy HeuristicAgent boards at random, and that
    randomness swamps everything else — two identical starts can finish 14
    stations apart on luck alone, which makes it useless for comparing start
    positions or reward settings. This one is near-deterministic, so a
    difference in the result is a difference in the setup.
    """

    def __init__(self, rng: random.Random, challenge_chip_floor: int = 12):
        self.rng = rng
        #: Below this many chips, grab any challenge at hand to refill.
        self.floor = challenge_chip_floor

    def decide(self, engine: Engine, team: TeamState, options: list[Option]) -> Decision:
        claim_amount = 0
        offer = engine.claim_offer(team)
        if offer is not None and offer.kind == "claim":
            claim_amount = offer.lo        # cheapest grab, always worth it

        best_walk = None
        for i, o in enumerate(options):
            if o.key != "walk":
                continue
            # Take it if we're short on chips, or it's a short detour.
            if team.chips <= self.floor or o.minutes <= 5:
                if best_walk is None or o.minutes < options[best_walk].minutes:
                    best_walk = i
        if best_walk is not None:
            o = options[best_walk]
            call = None
            if o.call_range:
                lo, hi = o.call_range
                from challenges import profile_for
                prof = profile_for(o.challenge or "")
                # Pick the call with the best expected value.
                call = max(range(lo, hi + 1), key=lambda n: n * prof.success_prob(n))
            return Decision(best_walk, claim_amount=claim_amount, call_value=call,
                            notes="explorer: challenge")

        # Head wherever the nearest not-mine station is.
        scored: list[tuple[int, int]] = []
        for i, o in enumerate(options):
            if o.key not in ("stay_on", "board") or o.line is None or o.direction is None:
                continue
            stops = engine.stops_to_claimable(team.station, o.line, o.direction, team)
            if stops is None:
                continue
            # Total minutes to reach it: this hop plus the remaining stops.
            cost = o.minutes + (stops - 1) * engine.cfg.minutes_per_segment
            scored.append((cost, i))
        if scored:
            scored.sort()
            return Decision(scored[0][1], claim_amount=claim_amount, notes="explorer: outward")

        rides = [i for i, o in enumerate(options) if o.key in ("stay_on", "board")]
        if rides:
            return Decision(self.rng.choice(rides), claim_amount=claim_amount,
                            notes="explorer: no target, keep moving")
        return Decision(0, claim_amount=claim_amount, notes="explorer: stuck")
