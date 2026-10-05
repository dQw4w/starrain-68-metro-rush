"""The game simulation.

Runs minute by minute. A team is always doing exactly one of: riding, walking,
running a challenge, or standing on a platform. Whenever a team finishes
whatever it was doing, the engine builds the list of legal things it could do
next and asks the agent to pick one. Everything else — travel time, chip
arithmetic, challenge outcomes — is resolved by the rules here, never by the
model.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from challenges import profile_for
from config import SimConfig
from network import ChallengeSite, Network


# --- actions -----------------------------------------------------------------

@dataclass
class Option:
    key: str                      # 'claim' | 'topup' | 'board' | 'stay_on' | 'walk' | 'wait'
    label: str                    # what the agent reads
    minutes: int                  # time this burns
    line: str | None = None
    direction: int | None = None
    to_station: str | None = None
    challenge: str | None = None
    amount: int | None = None     # claim/top-up chips
    call_range: tuple[int, int] | None = None   # call-your-shot bounds


@dataclass
class Decision:
    option_index: int
    call_value: int | None = None
    amount: int | None = None
    notes: str = ""


# --- state -------------------------------------------------------------------

@dataclass
class TeamState:
    name: str
    chips: int
    station: str
    mode: str = "idle"            # idle | riding | walking | challenge
    line: str | None = None       # line currently aboard
    direction: int | None = None
    busy_until: int = 0
    walking_to: str | None = None          # challenge name
    challenge_running: str | None = None
    challenge_call: int | None = None
    notes: str = ""
    attempted: set[str] = field(default_factory=set)
    llm_calls: int = 0
    log: list[str] = field(default_factory=list)


@dataclass
class StationClaim:
    owner: str | None = None
    value: int = 0
    cap: int = 0


@dataclass
class GameResult:
    minutes: int
    teams: dict[str, dict]
    station_gap: int
    chip_gap: int
    transcript: list[str]


class Engine:
    def __init__(self, cfg: SimConfig, net: Network, agents: dict, rng: random.Random):
        self.cfg = cfg
        self.net = net
        self.agents = agents          # team name -> agent with .decide(...)
        self.rng = rng
        self.minute = 0
        self.transcript: list[str] = []

        self.teams = {
            name: TeamState(name=name, chips=cfg.starting_chips[name], station=cfg.start_stations[name])
            for name in cfg.starting_chips
        }
        self.claims: dict[str, StationClaim] = {s: StationClaim() for s in net.all_stations}
        # name -> 'active' | 'retired'
        self.challenge_state = {c.name: "active" for c in net.challenges}
        self.challenge_fails: dict[str, int] = {c.name: 0 for c in net.challenges}

    # --- helpers -----------------------------------------------------------

    def _say(self, msg: str) -> None:
        self.transcript.append(f"[{self.minute:>3}m] {msg}")

    def stations_owned(self, team: str) -> int:
        return sum(1 for c in self.claims.values() if c.owner == team)

    def _deposit_bounds(self, kind: str, claim: StationClaim) -> tuple[int, int]:
        """Mirrors game_logic._deposit_bounds: a claim overwrites and gets a
        fresh ceiling, a top-up adds up to the frozen cap."""
        if kind == "claim":
            return claim.value + 1, claim.value + self.cfg.max_deposit_per_visit
        return 1, claim.cap - claim.value

    def available_challenges(self, team: TeamState) -> set[str]:
        return {
            n for n, st in self.challenge_state.items()
            if st == "active" and n not in team.attempted
        }

    # --- option building ---------------------------------------------------

    def options_for(self, team: TeamState) -> list[Option]:
        cfg, net = self.cfg, self.net
        opts: list[Option] = []

        # Still aboard a train that just pulled in: riding on is an option.
        if team.mode == "riding" and team.line is not None and team.direction is not None:
            nxt = net.neighbour(team.station, team.line, team.direction)
            if nxt is not None:
                opts.append(Option(
                    key="stay_on",
                    label=f"留在車上，繼續搭 {net.line_names.get(team.line, team.line)} 到「{nxt}」",
                    minutes=cfg.minutes_per_segment,
                    line=team.line, direction=team.direction, to_station=nxt,
                ))

        claim = self.claims[team.station]
        if claim.owner == team.name:
            lo, hi = self._deposit_bounds("topup", claim)
            if hi >= lo and team.chips >= lo:
                amount = min(hi, team.chips)
                opts.append(Option(
                    key="topup",
                    label=f"在「{team.station}」加碼 {lo}~{min(hi, team.chips)} 枚（目前 {claim.value}/{claim.cap}）",
                    minutes=cfg.claim_minutes, amount=amount,
                ))
        else:
            lo, hi = self._deposit_bounds("claim", claim)
            if team.chips >= lo:
                amount = min(hi, team.chips)
                held = f"（目前 {claim.owner or '無人'} 持有，站上 {claim.value} 枚）"
                opts.append(Option(
                    key="claim",
                    label=f"佔領「{team.station}」，投入 {lo}~{min(hi, team.chips)} 枚 {held}",
                    minutes=cfg.claim_minutes, amount=amount,
                ))

        for line, direction, nxt in net.ride_options(team.station):
            # Boarding the line you're already on in the same direction is
            # just 'stay_on', already offered above.
            if team.mode == "riding" and line == team.line and direction == team.direction:
                continue
            cost = net.board_cost(team.station, team.line if team.mode == "riding" else None, line)
            opts.append(Option(
                key="board",
                label=f"搭 {net.line_names.get(line, line)} 往「{net.terminus(line, direction)}」方向，下一站「{nxt}」",
                minutes=cost + cfg.minutes_per_segment,
                line=line, direction=direction, to_station=nxt,
            ))

        for ch, walk in net.nearest_challenges(
            team.station, self.available_challenges(team), cfg.max_challenge_options
        ):
            prof = profile_for(ch.name)
            reward = self._describe_reward(ch)
            opts.append(Option(
                key="walk",
                label=(f"步行 {walk} 分鐘去做任務「{ch.name}」（{ch.location_name}）"
                       f"：{reward}，預計現場約 {round(prof.mean_minutes)} 分鐘"),
                minutes=walk, challenge=ch.name, call_range=prof.call_range,
            ))

        opts.append(Option(key="wait", label=f"原地等待 {cfg.idle_wait_minutes} 分鐘",
                           minutes=cfg.idle_wait_minutes))
        return opts

    def _describe_reward(self, ch: ChallengeSite) -> str:
        rc = ch.reward_config
        if ch.type == "fixed":
            return f"固定 {rc.get('chips')} 枚"
        if ch.type == "variable":
            return f"call your shot，每單位 {rc.get('chips_per_unit')} 枚"
        if ch.type == "steal":
            return f"偷取對手 {rc.get('steal_pct')}%"
        if ch.type == "multiplier":
            return f"己隊代幣 +{rc.get('multiplier_pct')}%"
        return str(rc)

    # --- applying a decision ------------------------------------------------

    def apply(self, team: TeamState, opt: Option, decision: Decision) -> None:
        cfg = self.cfg
        if decision.notes:
            team.notes = decision.notes

        if opt.key in ("stay_on", "board"):
            team.mode = "riding"
            team.line, team.direction = opt.line, opt.direction
            team.station = opt.to_station or team.station
            team.busy_until = self.minute + opt.minutes
            return

        if opt.key in ("claim", "topup"):
            claim = self.claims[team.station]
            lo, hi = self._deposit_bounds(opt.key, claim)
            hi = min(hi, team.chips)
            amount = decision.amount if decision.amount is not None else (opt.amount or lo)
            amount = max(lo, min(hi, int(amount)))
            if amount < lo or team.chips < amount:
                team.busy_until = self.minute + 1       # couldn't afford it after all
                team.mode = "idle"
                return
            if opt.key == "claim":
                claim.cap = claim.value + cfg.max_deposit_per_visit
                claim.value = amount
                claim.owner = team.name
            else:
                claim.value += amount
            team.chips -= amount
            team.mode = "idle"
            team.busy_until = self.minute + opt.minutes
            self._say(f"{team.name} 在「{team.station}」{'佔領' if opt.key == 'claim' else '加碼'} "
                      f"{amount} 枚（剩 {team.chips}）")
            return

        if opt.key == "walk":
            team.mode = "walking"
            team.walking_to = opt.challenge
            team.challenge_call = decision.call_value
            team.busy_until = self.minute + opt.minutes
            return

        team.mode = "idle"
        team.busy_until = self.minute + opt.minutes

    # --- events -------------------------------------------------------------

    def _finish_walk(self, team: TeamState) -> None:
        name = team.walking_to
        team.walking_to = None
        if name is None or self.challenge_state.get(name) != "active":
            team.mode = "idle"                           # someone finished it first
            team.busy_until = self.minute + 1
            return
        prof = profile_for(name)
        team.mode = "challenge"
        team.challenge_running = name
        team.busy_until = self.minute + prof.sample_minutes(self.rng)
        self._say(f"{team.name} 抵達「{name}」開始挑戰"
                  + (f"（喊出 {team.challenge_call}）" if team.challenge_call is not None else ""))

    def _finish_challenge(self, team: TeamState) -> None:
        name = team.challenge_running
        team.challenge_running = None
        team.mode = "idle"
        team.busy_until = self.minute + 1
        if name is None:
            return
        ch = next(c for c in self.net.challenges if c.name == name)
        prof = profile_for(name)
        team.attempted.add(name)

        p = prof.success_prob(team.challenge_call)
        won = self.rng.random() < p
        bonus = 1 + (self.challenge_fails[name] * self.cfg.fail_bonus_step_pct) / 100

        if not won:
            self.challenge_fails[name] += 1
            self._say(f"{team.name} 任務「{name}」失敗（p={p:.2f}）")
            team.challenge_call = None
            return

        reward = self._payout(team, ch, team.challenge_call, bonus)
        self.challenge_state[name] = "retired"
        self._say(f"{team.name} 任務「{name}」成功（p={p:.2f}），+{reward} 枚 → {team.chips}")
        team.challenge_call = None

    def _payout(self, team: TeamState, ch: ChallengeSite, called: int | None, bonus: float) -> int:
        """Mirrors game_logic._compute_reward."""
        rc = ch.reward_config
        if ch.type == "fixed":
            gain = round(rc.get("chips", 0) * bonus)
        elif ch.type == "variable":
            gain = round((called or 0) * rc.get("chips_per_unit", 0) * bonus)
        elif ch.type == "multiplier":
            gain = math.floor(max(0, team.chips) * (rc.get("multiplier_pct", 0) * bonus) / 100)
        elif ch.type == "steal":
            victim = max((t for t in self.teams.values() if t.name != team.name),
                         key=lambda t: t.chips, default=None)
            if victim is None:
                return 0
            gain = math.floor(max(0, victim.chips) * (rc.get("steal_pct", 0) * bonus) / 100)
            victim.chips -= gain
        else:
            gain = 0
        team.chips += gain
        return gain

    # --- main loop -----------------------------------------------------------

    def run(self) -> GameResult:
        cfg = self.cfg
        for minute in range(cfg.game_minutes + 1):
            self.minute = minute
            for team in self.teams.values():
                if team.busy_until > minute:
                    continue
                if team.mode == "walking":
                    self._finish_walk(team)
                    continue
                if team.mode == "challenge":
                    self._finish_challenge(team)
                    continue
                if minute >= cfg.game_minutes:
                    continue
                self._take_turn(team)
        return self._result()

    def _take_turn(self, team: TeamState) -> None:
        opts = self.options_for(team)
        if not opts:
            team.busy_until = self.minute + 1
            return
        agent = self.agents[team.name]
        decision = agent.decide(self, team, opts)
        opt = opts[max(0, min(len(opts) - 1, decision.option_index))]
        self.apply(team, opt, decision)

    def _result(self) -> GameResult:
        summary = {
            t.name: {
                "chips": t.chips,
                "stations": self.stations_owned(t.name),
                "attempted": len(t.attempted),
                "llm_calls": t.llm_calls,
                "notes": t.notes,
            }
            for t in self.teams.values()
        }
        names = list(summary)
        a, b = summary[names[0]], summary[names[1]]
        return GameResult(
            minutes=self.cfg.game_minutes,
            teams=summary,
            station_gap=abs(a["stations"] - b["stations"]),
            chip_gap=abs(a["chips"] - b["chips"]),
            transcript=self.transcript,
        )
