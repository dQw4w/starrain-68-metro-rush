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
    """A movement choice. Claiming is not one of these — you tap your phone
    while standing on the platform, so it happens alongside whatever you do
    next rather than instead of it (see ClaimOffer / Decision.claim_amount)."""
    key: str                      # 'board' | 'stay_on' | 'walk' | 'wait'
    label: str
    minutes: int
    line: str | None = None
    direction: int | None = None
    to_station: str | None = None
    challenge: str | None = None
    call_range: tuple[int, int] | None = None   # call-your-shot bounds


@dataclass
class ClaimOffer:
    kind: str                     # 'claim' | 'topup'
    lo: int
    hi: int
    label: str


@dataclass
class Decision:
    option_index: int             # index into the movement options
    claim_amount: int = 0         # 0 = don't claim/top-up this turn
    call_value: int | None = None
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
    #: Last few stations stood at — fed back so the agent can see itself
    #: ping-ponging between the same two stations.
    recent_stations: list[str] = field(default_factory=list)
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
        # name -> 'active' | 'queued' | 'retired'
        if cfg.all_challenges_active:
            self.challenge_state = {c.name: "active" for c in net.challenges}
        else:
            # Mirror activate_initial_pool(): the opening reveal is
            # fixed-reward challenges only, the rest wait in the backlog.
            self.challenge_state = {c.name: "queued" for c in net.challenges}
            if cfg.initial_active_challenges:
                known = {c.name for c in net.challenges}
                for name in cfg.initial_active_challenges:
                    if name not in known:
                        raise ValueError(
                            f"initial_active_challenges 裡的「{name}」不存在於 seed_challenges.py"
                        )
                    self.challenge_state[name] = "active"
            else:
                fixed = [c.name for c in net.challenges if c.type == "fixed"]
                rng.shuffle(fixed)
                for name in fixed[: cfg.challenge_pool_initial]:
                    self.challenge_state[name] = "active"
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

    def claim_offer(self, team: TeamState) -> ClaimOffer | None:
        """What this team could pay into the station it's standing at, right
        now. Costs chips but no time — it happens while they're waiting for
        the train — so it's offered alongside the movement choice, not
        instead of it."""
        claim = self.claims[team.station]
        if claim.owner == team.name:
            lo, hi = self._deposit_bounds("topup", claim)
            hi = min(hi, team.chips)
            if hi < lo:
                return None
            return ClaimOffer("topup", lo, hi,
                              f"在「{team.station}」加碼（目前 {claim.value}/{claim.cap}，"
                              f"可投入 {lo}~{hi} 枚；加碼不會增加車站數，只是讓對手更難搶）")
        lo, hi = self._deposit_bounds("claim", claim)
        hi = min(hi, team.chips)
        if hi < lo:
            return None
        held = "目前無人佔領" if claim.owner is None else f"目前是 {claim.owner} 的，站上 {claim.value} 枚"
        return ClaimOffer("claim", lo, hi,
                          f"佔領「{team.station}」（{held}；投入 {lo}~{hi} 枚，車站數 +1）")

    def options_for(self, team: TeamState) -> list[Option]:
        cfg, net = self.cfg, self.net
        opts: list[Option] = []

        # Still aboard a train that just pulled in: riding on is an option.
        if team.mode == "riding" and team.line is not None and team.direction is not None:
            nxt = net.neighbour(team.station, team.line, team.direction)
            if nxt is not None:
                opts.append(Option(
                    key="stay_on",
                    label=(f"留在車上，繼續搭 {net.line_names.get(team.line, team.line)} 到"
                           f"「{nxt}」{self._station_tag(nxt, team)}"
                           f"{self._lookahead(team.station, team.line, team.direction, team)}"),
                    minutes=cfg.minutes_per_segment,
                    line=team.line, direction=team.direction, to_station=nxt,
                ))

        for line, direction, nxt in net.ride_options(team.station):
            # Boarding the line you're already on in the same direction is
            # just 'stay_on', already offered above.
            if team.mode == "riding" and line == team.line and direction == team.direction:
                continue
            cost = net.board_cost(team.station, team.line if team.mode == "riding" else None, line)
            opts.append(Option(
                key="board",
                label=(f"搭 {net.line_names.get(line, line)} 往「{net.terminus(line, direction)}」方向，"
                       f"下一站「{nxt}」{self._station_tag(nxt, team)}"
                       f"{self._lookahead(team.station, line, direction, team)}"),
                minutes=cost + cfg.minutes_per_segment,
                line=line, direction=direction, to_station=nxt,
            ))

        walk_opts: list[Option] = []
        for ch, walk, is_drop_off in net.nearest_challenges(
            team.station, self.available_challenges(team), cfg.max_challenge_options
        ):
            prof = profile_for(ch.name)
            reward = self._describe_reward(ch)
            star = "★ 這站就是這個任務最近的下車點，錯過就要繞回來！" if is_drop_off else ""
            walk_opts.append(Option(
                key="walk",
                label=(f"{star}下車步行 {walk} 分鐘去做任務「{ch.name}」（{ch.location_name}）"
                       f"：{reward}，預計現場約 {round(prof.mean_minutes)} 分鐘"),
                minutes=walk, challenge=ch.name, call_range=prof.call_range,
            ))
        # Challenges are the only way to earn chips back, so they lead the
        # list rather than being buried under half a dozen ride options.
        opts = walk_opts + opts

        if not opts:
            # Only when there is genuinely nothing else — otherwise waiting
            # becomes the agent's favourite move, and it is never correct:
            # there is no mechanic that rewards standing still.
            opts.append(Option(key="wait", label=f"原地等待 {cfg.idle_wait_minutes} 分鐘",
                               minutes=cfg.idle_wait_minutes))
        return opts

    def stops_to_claimable(self, station: str, line: str, direction: int,
                            team: TeamState) -> int | None:
        """How many stops down this line until a station this team doesn't
        already own. None if it's all theirs to the end of the line."""
        order = self.net.line_stations.get(line) or []
        if station not in order:
            return None
        i = order.index(station)
        for stops in range(1, 15):
            j = i + direction * stops
            if not 0 <= j < len(order):
                return None
            if self.claims[order[j]].owner != team.name:
                return stops
        return None

    def _lookahead(self, station: str, line: str, direction: int, team: TeamState) -> str:
        """What's worth travelling toward down this line. Without it, a team
        sitting in the middle of its own territory sees nothing but its own
        full stations one stop ahead and concludes there is nowhere to go."""
        order = self.net.line_stations.get(line) or []
        if station not in order:
            return ""
        i = order.index(station)
        for stops in range(1, 15):
            j = i + direction * stops
            if not 0 <= j < len(order):
                break
            nxt = order[j]
            owner = self.claims[nxt].owner
            if owner is None:
                return f"　→ 這個方向第 {stops} 站「{nxt}」無人佔領，可以去吃"
            if owner != team.name:
                return f"　→ 這個方向第 {stops} 站「{nxt}」是對手的，可以去搶"
        return "　→ 這個方向前面都是你自己的站了"

    def _station_tag(self, station: str, team: TeamState) -> str:
        """Whether a destination is worth getting off at, spelled out — the
        agent otherwise can't tell a free station from one it already owns,
        and ends up shuttling between its own two stations 'defending' them."""
        claim = self.claims[station]
        if claim.owner is None:
            return "（無人佔領，可用 1 枚佔下 ✅）"
        if claim.owner == team.name:
            if claim.value >= claim.cap:
                return "（你的站，已滿；路過沒關係，但別為了它專程折返）"
            return f"（你的站，{claim.value}/{claim.cap}，還能加碼）"
        return f"（{claim.owner} 的站，站上 {claim.value} 枚，要 {claim.value + 1} 枚才搶得下 ⚔️）"

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

    def _apply_claim(self, team: TeamState, amount: int) -> None:
        """Costs chips, not time — the team taps it in while they're standing
        on the platform, so it never competes with the movement choice."""
        offer = self.claim_offer(team)
        if offer is None or amount <= 0:
            return
        amount = max(offer.lo, min(offer.hi, int(amount)))
        claim = self.claims[team.station]
        if offer.kind == "claim":
            claim.cap = claim.value + self.cfg.max_deposit_per_visit
            claim.value = amount
            claim.owner = team.name
        else:
            claim.value += amount
        team.chips -= amount
        self._say(f"{team.name} 在「{team.station}」{'佔領' if offer.kind == 'claim' else '加碼'} "
                  f"{amount} 枚（剩 {team.chips}）")

    def apply(self, team: TeamState, opt: Option, decision: Decision) -> None:
        if decision.notes:
            team.notes = decision.notes

        # Claim first: it's free in time, so it stacks with whatever move
        # they picked in the same reply.
        self._apply_claim(team, decision.claim_amount)

        if opt.key in ("stay_on", "board"):
            team.mode = "riding"
            team.line, team.direction = opt.line, opt.direction
            team.station = opt.to_station or team.station
            team.recent_stations = (team.recent_stations + [team.station])[-8:]
            team.busy_until = self.minute + opt.minutes
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
        self._refill_pool()
        self._say(f"{team.name} 任務「{name}」成功（p={p:.2f}），+{reward} 枚 → {team.chips}")
        team.challenge_call = None

    def _refill_pool(self) -> None:
        """Mirrors game_logic._refill_pool: a completed challenge pulls more
        off the backlog, any type this time. No-op when the pool is already
        fully revealed."""
        if self.cfg.all_challenges_active:
            return
        queued = [n for n, st in self.challenge_state.items() if st == "queued"]
        if not queued:
            return
        self.rng.shuffle(queued)
        for name in queued[: self.cfg.challenge_pool_refill]:
            self.challenge_state[name] = "active"
            self._say(f"新任務公佈：「{name}」")

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
