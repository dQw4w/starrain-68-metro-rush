"""A learned player: a small numpy MLP that scores every legal move.

The engine already hands an agent the full list of legal moves each turn, so
the policy doesn't need to know the rules — it only has to rank options. Each
option is turned into a feature vector (what kind of move, where it goes,
what's there, how much closer it gets you to the best challenge or the
nearest station you could take) concatenated with the team's situation
(chips, time left, the score), and the network gives it one number. Highest
number wins. Two small extra heads decide the parts of a turn that aren't a
movement choice: how much to put down when claiming or topping up, and how
much risk to take on a call-your-shot number.

All weights live in one flat vector, which is what evolution strategies
perturbs. No gradients, no autograd — the game isn't differentiable anyway.
"""
from __future__ import annotations

import math

import numpy as np

from challenges import profile_for
from engine import Decision, Engine, Option, TeamState
from fairness import travel_times

N_GLOBAL = 8
N_OPTION = 18
N_OFFER = 5
HIDDEN = 32

# Flat-vector layout.
_SHAPES = [
    ("w1", (N_OPTION + N_GLOBAL, HIDDEN)),
    ("b1", (HIDDEN,)),
    ("w2", (HIDDEN,)),
    ("claim_w", (N_GLOBAL + N_OFFER,)),
    ("claim_b", (1,)),
    ("risk", (1,)),
]
N_PARAMS = sum(int(np.prod(s)) for _, s in _SHAPES)


def unpack(theta: np.ndarray) -> dict[str, np.ndarray]:
    out, i = {}, 0
    for name, shape in _SHAPES:
        n = int(np.prod(shape))
        out[name] = theta[i:i + n].reshape(shape)
        i += n
    return out


def init_params(rng: np.random.Generator) -> np.ndarray:
    theta = np.zeros(N_PARAMS)
    p = unpack(theta)
    p["w1"][:] = rng.normal(0, 1 / math.sqrt(N_OPTION + N_GLOBAL), p["w1"].shape)
    p["w2"][:] = rng.normal(0, 1 / math.sqrt(HIDDEN), p["w2"].shape)
    return theta


# Travel times only depend on the network, never on rewards or chips, so one
# all-pairs table per process serves every game that process plays.
_TT: dict[str, dict[str, int]] | None = None


def _tt(engine: Engine) -> dict[str, dict[str, int]]:
    global _TT
    if _TT is None:
        _TT = {s: travel_times(engine.net, engine.cfg, s) for s in engine.net.all_stations}
    return _TT


def expected_chips(engine: Engine, team: TeamState, ch) -> float:
    prof = profile_for(ch.name)
    rc = ch.reward_config
    if ch.type == "fixed":
        return rc.get("chips", 0) * prof.success
    if ch.type == "variable":
        lo, hi = prof.call_range or (1, 1)
        per = rc.get("chips_per_unit", 0)
        return max(n * per * prof.success_prob(n) for n in range(lo, hi + 1))
    if ch.type == "steal":
        richest = max((t.chips for t in engine.teams.values() if t.name != team.name), default=0)
        return richest * rc.get("steal_pct", 0) / 100 * prof.success
    return 0.0


class NeuralAgent:
    def __init__(self, theta: np.ndarray):
        self.p = unpack(np.asarray(theta, dtype=float))

    # --- features ------------------------------------------------------------

    def _globals(self, engine: Engine, team: TeamState) -> np.ndarray:
        opp = next(t for t in engine.teams.values() if t.name != team.name)
        mine = engine.stations_owned(team.name)
        theirs = engine.stations_owned(opp.name)
        return np.array([
            team.chips / 30,
            opp.chips / 30,
            (engine.cfg.game_minutes - engine.minute) / engine.cfg.game_minutes,
            mine / 40,
            (mine - theirs) / 10,
            len(engine.available_challenges(team)) / 10,
            1.0 if team.mode == "riding" else 0.0,
            1.0,
        ])

    def _targets(self, engine: Engine, team: TeamState):
        """The best challenge by chips per minute from here, and every station
        this team doesn't own — what a ride can be getting you closer to."""
        tt = _tt(engine)
        here = tt[team.station]
        best_stn, best_rate = None, 0.0
        for ch in engine.net.challenges:
            if ch.name not in engine.available_challenges(team):
                continue
            stn, walk = engine.net.nearest_station_to(ch)
            rate = expected_chips(engine, team, ch) / max(1, here.get(stn, 999) + walk + profile_for(ch.name).mean_minutes)
            if rate > best_rate:
                best_stn, best_rate = stn, rate
        not_mine = [s for s, c in engine.claims.items() if c.owner != team.name]
        return best_stn, best_rate, not_mine

    def _option(self, engine: Engine, team: TeamState, o: Option, targets) -> np.ndarray:
        tt = _tt(engine)
        best_stn, best_rate, not_mine = targets
        f = np.zeros(N_OPTION)
        f[["board", "stay_on", "walk", "wait"].index(o.key)] = 1.0
        f[4] = o.minutes / 10
        if o.key in ("board", "stay_on") and o.to_station:
            claim = engine.claims[o.to_station]
            if claim.owner is None:
                f[5] = 1.0
            elif claim.owner == team.name:
                f[6 if claim.value < claim.cap else 7] = 1.0
            else:
                f[8] = 1.0
                f[9] = (claim.value + 1) / 10
            stops = engine.stops_to_claimable(team.station, o.line, o.direction, team)
            f[10] = 1 / stops if stops else 0.0
            here, there = tt[team.station], tt[o.to_station]
            if best_stn is not None:
                # Minutes saved toward the best challenge, net of this hop.
                f[11] = (here.get(best_stn, 999) - (o.minutes + there.get(best_stn, 999))) / 10
                f[12] = best_rate
            if not_mine:
                f[13] = (min(here.get(s, 999) for s in not_mine)
                         - (o.minutes + min(there.get(s, 999) for s in not_mine))) / 10
        elif o.key == "walk" and o.challenge:
            ch = next(c for c in engine.net.challenges if c.name == o.challenge)
            prof = profile_for(ch.name)
            ev = expected_chips(engine, team, ch)
            f[14] = ev / 10
            f[15] = ev / max(1, o.minutes + prof.mean_minutes)
            f[16] = {"fixed": 0.0, "variable": 0.5, "steal": 1.0}.get(ch.type, 0.0)
            f[17] = prof.mean_minutes / 10
        return f

    # --- decisions -------------------------------------------------------------

    def features(self, engine: Engine, team: TeamState, options: list[Option]) -> np.ndarray:
        """One row per option: option features then the team's situation."""
        g = self._globals(engine, team)
        targets = self._targets(engine, team)
        return np.stack([np.concatenate([self._option(engine, team, o, targets), g]) for o in options])

    def decide(self, engine: Engine, team: TeamState, options: list[Option]) -> Decision:
        p = self.p
        x = self.features(engine, team, options)
        g = x[0, N_OPTION:]
        scores = np.tanh(x @ p["w1"] + p["b1"]) @ p["w2"]
        idx = int(np.argmax(scores))

        claim_amount = 0
        offer = engine.claim_offer(team)
        if offer is not None:
            claim = engine.claims[team.station]
            of = np.array([
                1.0 if offer.kind == "claim" else 0.0,
                offer.lo / 5,
                offer.hi / 5,
                1.0 if claim.owner not in (None, team.name) else 0.0,
                claim.value / 5,
            ])
            frac = 1 / (1 + math.exp(-float(np.concatenate([g, of]) @ p["claim_w"] + p["claim_b"][0])))
            # Below 10% it passes on the offer entirely — sometimes the right
            # call when chips are short and the station isn't contested; the
            # rest of the range maps onto lo..hi.
            if frac >= 0.1 and team.chips >= offer.lo:
                extra = round((frac - 0.1) / 0.9 * (offer.hi - offer.lo))
                claim_amount = min(team.chips, offer.lo + extra)

        call = None
        o = options[idx]
        if o.call_range:
            lo, hi = o.call_range
            prof = profile_for(o.challenge or "")
            # risk > 1 weights success probability harder (plays safe); < 1
            # chases big numbers. Bounded so a bad mutation can't go silly.
            r = math.exp(max(-1.5, min(1.5, float(p["risk"][0]))))
            call = max(range(lo, hi + 1), key=lambda n: n * prof.success_prob(n) ** r)
        return Decision(idx, claim_amount=claim_amount, call_value=call, notes="neural")
