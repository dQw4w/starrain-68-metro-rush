"""The decision makers.

`LLMAgent` hands the local model the current game state plus a numbered list
of legal options and takes back a number. `HeuristicAgent` plays a plain
greedy game with no model at all — useful as a baseline, as a sanity check
that the engine itself is sane, and as the fallback whenever the model
returns something unparseable.
"""
from __future__ import annotations

import random

from engine import Decision, Engine, Option, TeamState
from llm import LLMClient, LLMError, extract_json

SYSTEM_PROMPT = """你是一個捷運大富翁類遊戲的玩家，正在指揮一支小隊。

遊戲規則重點：
- 目標：遊戲結束時「擁有的車站數」越多越好，其次才是手上剩的代幣。
- 佔領車站要投入代幣，投入後代幣就花掉了，但那座車站算你的。
- 對手可以用更多代幣把你的車站搶走，加碼可以把站養高一點讓對手更難搶。
- 任務可以賺代幣，但要花時間走過去和進行，而且可能失敗。
- 時間是最稀缺的資源，搭車和走路都要花分鐘數。

你每次只會看到目前狀態和一組可選動作，請選一個。

回覆必須是 JSON，格式：
{"option": <選項編號>, "amount": <投入代幣數，只有佔領/加碼時需要>, "call": <喊出的數量，只有 call your shot 任務需要>, "notes": "<給自己看的策略筆記>"}

只輸出 JSON，不要有其他文字。"""


def _state_block(engine: Engine, team: TeamState) -> str:
    me = team
    others = [t for t in engine.teams.values() if t.name != team.name]
    lines = [
        f"遊戲時間：第 {engine.minute} 分鐘 / 共 {engine.cfg.game_minutes} 分鐘"
        f"（剩 {engine.cfg.game_minutes - engine.minute} 分鐘）",
        f"你是：{me.name}",
        f"你的代幣：{me.chips} 枚｜你的車站數：{engine.stations_owned(me.name)}",
    ]
    for o in others:
        lines.append(f"對手 {o.name}：{o.chips} 枚｜{engine.stations_owned(o.name)} 站")
    lines.append(f"你現在位置：「{me.station}」" + ("（在車上，剛到站）" if me.mode == "riding" else "（在站內）"))

    mine = [s for s, c in engine.claims.items() if c.owner == me.name]
    if mine:
        lines.append("你擁有的車站：" + "、".join(
            f"{s}({engine.claims[s].value}/{engine.claims[s].cap})" for s in mine[:12]
        ) + (" …" if len(mine) > 12 else ""))
    remaining = sum(1 for st in engine.challenge_state.values() if st == "active")
    lines.append(f"還沒被解掉的任務：{remaining} 個")
    if me.notes:
        lines.append(f"你上次寫下的策略筆記：{me.notes}")
    return "\n".join(lines)


def _options_block(options: list[Option]) -> str:
    out = []
    for i, o in enumerate(options):
        extra = ""
        if o.key in ("claim", "topup"):
            extra = "（請用 amount 指定投入幾枚）"
        elif o.call_range:
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

        # Grab an unowned/cheap station while standing on it.
        for i, o in by_key.get("claim", []):
            claim = engine.claims[team.station]
            if claim.owner is None and team.chips >= claim.value + 1:
                return Decision(i, amount=claim.value + 1, notes="greedy: take free station")

        # Otherwise a short walk to a challenge, if one is close.
        walks = sorted(by_key.get("walk", []), key=lambda t: t[1].minutes)
        if walks and walks[0][1].minutes <= 10:
            i, o = walks[0]
            call = None
            if o.call_range:
                lo, hi = o.call_range
                call = lo + (hi - lo) // 4          # conservative call
            return Decision(i, call_value=call, notes="greedy: nearby challenge")

        if "stay_on" in by_key:
            return Decision(by_key["stay_on"][0][0], notes="greedy: ride on")
        boards = by_key.get("board", [])
        if boards:
            return Decision(self.rng.choice(boards)[0], notes="greedy: board something")
        return Decision(len(options) - 1, notes="greedy: wait")


class LLMAgent:
    def __init__(self, client: LLMClient, fallback: HeuristicAgent, max_calls: int = 0):
        self.client = client
        self.fallback = fallback
        self.max_calls = max_calls

    def decide(self, engine: Engine, team: TeamState, options: list[Option]) -> Decision:
        if self.max_calls and team.llm_calls >= self.max_calls:
            return self.fallback.decide(engine, team, options)

        prompt = f"{_state_block(engine, team)}\n\n可選動作：\n{_options_block(options)}\n\n請選擇一個動作並回覆 JSON。"
        try:
            raw = self.client.chat(SYSTEM_PROMPT, prompt)
        except LLMError as e:
            print(f"  ! LLM error, falling back to heuristic: {e}")
            return self.fallback.decide(engine, team, options)
        team.llm_calls += 1
        if self.client.cfg.verbose:
            print(f"\n--- {team.name} @ {engine.minute}m ---\n{prompt}\n--> {raw.strip()[:400]}")

        parsed = extract_json(raw)
        if parsed is None or "option" not in parsed:
            return self.fallback.decide(engine, team, options)

        try:
            idx = int(parsed["option"])
        except (TypeError, ValueError):
            return self.fallback.decide(engine, team, options)
        if not 0 <= idx < len(options):
            return self.fallback.decide(engine, team, options)

        opt = options[idx]
        call = None
        if opt.call_range:
            lo, hi = opt.call_range
            try:
                call = max(lo, min(hi, int(parsed.get("call", lo))))
            except (TypeError, ValueError):
                call = lo
        amount = None
        if opt.key in ("claim", "topup") and parsed.get("amount") is not None:
            try:
                amount = int(parsed["amount"])
            except (TypeError, ValueError):
                amount = None
        notes = str(parsed.get("notes", ""))[:400]
        return Decision(idx, call_value=call, amount=amount, notes=notes)
