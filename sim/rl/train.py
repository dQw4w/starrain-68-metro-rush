"""Adversarial tuning: players learn to win, the game learns to be close.

Two optimisers take turns, GAN-style:

  * Players (rl/policy.py's NeuralAgent) are trained by evolution strategies
    to WIN — against a pool of their own past selves plus the rule-based
    ExplorerAgent, with start stations randomised, so the policy can't just
    learn one side of the map. Reward is the win (1 / 0.5 / 0) plus a little
    for the station margin so early training has a slope to climb.

  * The designer is trained by the cross-entropy method over the game's
    knobs — starting chips and a multiplier on every challenge's reward —
    to make games between those players CLOSE, UNBIASED between the two
    starts, and FULL OF CHALLENGES:

        J = - w_gap   * E|station gap|
            - w_bias  * |E[台北車站 - 公館 stations]|
            + w_chal  * E[challenges attempted, both teams]
            - w_reg   * mean(log-multiplier^2)

    The regulariser keeps it near the hand-balanced rewards in
    seed_challenges.py, so it tunes them rather than throwing them out.

Each round: a few ES steps for the players under the current design, then a
few CEM steps for the design against the current players. Strictly it's a
Stackelberg game more than a GAN (the designer moves, the players best-
respond), and the alternation is the usual cheap approximation of that.

    cd sim
    python3 -m rl.train --rounds 30                     # train, saves to rl/out/
    python3 -m rl.train --rounds 10 --resume            # keep going
    python3 -m rl.train --report                        # print the recommended rewards

Nothing here edits seed_challenges.py — --report prints the numbers, you
decide what to copy over.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import ExplorerAgent  # noqa: E402
from config import SimConfig  # noqa: E402
from engine import Engine  # noqa: E402
from network import Network  # noqa: E402
from rl.policy import N_PARAMS, NeuralAgent  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
A, B = "台北車站隊", "公館隊"          # first is the one the bias term is signed toward
REWARD_KEY = {"fixed": "chips", "variable": "chips_per_unit", "steal": "steal_pct",
              "multiplier": "multiplier_pct"}
MULT_LO, MULT_HI = math.log(0.5), math.log(2.0)
CHIPS_LO, CHIPS_HI = 15.0, 60.0


# --- design --------------------------------------------------------------------

def base_rewards() -> list[tuple[str, str, float]]:
    """(name, reward key, seeded value) for every challenge, in seed order."""
    net = Network(SimConfig())
    return [(c.name, REWARD_KEY[c.type], float(c.reward_config[REWARD_KEY[c.type]])) for c in net.challenges]


BASE = base_rewards()
N_DESIGN = len(BASE) + 1                 # one log-multiplier per challenge, then starting chips


def clip_design(d: np.ndarray) -> np.ndarray:
    d = d.copy()
    d[:-1] = np.clip(d[:-1], MULT_LO, MULT_HI)
    d[-1] = np.clip(d[-1], CHIPS_LO, CHIPS_HI)
    return d


def config_for(d: np.ndarray) -> SimConfig:
    cfg = SimConfig()
    cfg.challenge_reward_overrides = {
        name: {key: min(100.0, base * math.exp(m)) if key == "steal_pct" else base * math.exp(m)}
        for (name, key, base), m in zip(BASE, d[:-1])
    }
    chips = int(round(d[-1]))
    cfg.starting_chips = {k: chips for k in cfg.starting_chips}
    return cfg


def current_design() -> np.ndarray:
    d = np.zeros(N_DESIGN)
    d[-1] = next(iter(SimConfig().starting_chips.values()))
    return d


# --- one game --------------------------------------------------------------------

def play(job) -> dict:
    """job = (theta_for_A or None, theta_for_B or None, design, seed).
    None means the rule-based ExplorerAgent plays that side."""
    th_a, th_b, d, seed = job
    rng = random.Random(seed)
    cfg = config_for(d)
    net = Network(cfg)
    agents = {
        A: NeuralAgent(th_a) if th_a is not None else ExplorerAgent(rng),
        B: NeuralAgent(th_b) if th_b is not None else ExplorerAgent(rng),
    }
    r = Engine(cfg, net, agents, rng).run()
    return {"a": r.teams[A]["stations"], "b": r.teams[B]["stations"],
            "chal": r.teams[A]["attempted"] + r.teams[B]["attempted"]}


def _win(mine: int, theirs: int) -> float:
    return 1.0 if mine > theirs else 0.5 if mine == theirs else 0.0


# --- players: evolution strategies ----------------------------------------------------

def es_step(pool: mp.Pool, theta, opponents, d, args, rng: np.random.Generator, seed0: int):
    half = args.pop // 2
    eps = rng.normal(0, 1, (half, N_PARAMS))
    cands = np.concatenate([theta + args.sigma * eps, theta - args.sigma * eps])
    jobs, meta = [], []
    for ci, cand in enumerate(cands):
        for g in range(args.games):
            # Same opponent and same dice for every candidate in this step, so
            # the ranking compares candidates rather than who drew the weak
            # opponent.
            opp = opponents[g % len(opponents)]
            seed = seed0 + g
            if g % 2 == 0:              # alternate which start the candidate gets
                jobs.append((cand, opp, d, seed)); meta.append((ci, "a"))
            else:
                jobs.append((opp, cand, d, seed)); meta.append((ci, "b"))
    fit = np.zeros(len(cands))
    for (ci, side), res in zip(meta, pool.map(play, jobs, chunksize=4)):
        mine, theirs = (res["a"], res["b"]) if side == "a" else (res["b"], res["a"])
        fit[ci] += _win(mine, theirs) + 0.02 * (mine - theirs)
    fit /= args.games
    # Centred ranks: robust to the reward's scale and to outlier games.
    ranks = np.empty(len(fit)); ranks[np.argsort(fit)] = np.arange(len(fit))
    ranks = ranks / (len(fit) - 1) - 0.5
    grad = ((ranks[:half] - ranks[half:])[:, None] * eps).sum(0) / (half * args.sigma)
    return theta + args.lr * grad - args.lr * args.decay * theta, float(fit.mean())


# --- designer: cross-entropy method ---------------------------------------------------

def evaluate_designs(pool: mp.Pool, theta, designs, args, seed0: int) -> list[dict]:
    """Self-play with the current policy on both sides; same seeds for every
    design so differences between designs aren't just different dice."""
    jobs = [(theta, theta, d, seed0 + g) for d in designs for g in range(args.design_games)]
    res = pool.map(play, jobs, chunksize=4)
    out = []
    for i, d in enumerate(designs):
        rs = res[i * args.design_games:(i + 1) * args.design_games]
        signed = [r["a"] - r["b"] for r in rs]
        gap = float(np.mean(np.abs(signed)))
        bias = float(np.mean(signed))
        chal = float(np.mean([r["chal"] for r in rs]))
        reg = float(np.mean(d[:-1] ** 2))
        score = -args.w_gap * gap - args.w_bias * abs(bias) + args.w_chal * chal - args.w_reg * reg
        out.append({"score": score, "gap": gap, "bias": bias, "chal": chal, "reg": reg})
    return out


def cem_step(pool, theta, mu, sd, args, rng: np.random.Generator, seed0: int):
    designs = [clip_design(mu + sd * rng.normal(0, 1, N_DESIGN)) for _ in range(args.design_pop)]
    designs.append(clip_design(mu))                     # always re-score the current mean
    ev = evaluate_designs(pool, theta, designs, args, seed0)
    order = np.argsort([-e["score"] for e in ev])
    elite = np.stack([designs[i] for i in order[: max(2, args.design_pop // 4)]])
    new_mu = 0.7 * mu + 0.3 * elite.mean(0)
    new_sd = np.maximum(0.7 * sd + 0.3 * elite.std(0), args.min_sd)
    return clip_design(new_mu), new_sd, ev[-1]


# --- driver ----------------------------------------------------------------------

def save(state: dict) -> None:
    OUT.mkdir(exist_ok=True)
    np.save(OUT / "theta.npy", state["theta"])
    np.save(OUT / "pool.npy", np.stack(state["pool"]))
    json.dump({"mu": state["mu"].tolist(), "sd": state["sd"].tolist(), "round": state["round"]},
              open(OUT / "design.json", "w"), ensure_ascii=False, indent=1)


def load() -> dict:
    meta = json.load(open(OUT / "design.json"))
    return {"theta": np.load(OUT / "theta.npy"), "pool": list(np.load(OUT / "pool.npy")),
            "mu": np.array(meta["mu"]), "sd": np.array(meta["sd"]), "round": meta["round"]}


def vs_explorer(pool, theta, d, games: int, seed0: int) -> float:
    jobs = [(theta, None, d, seed0 + g) if g % 2 == 0 else (None, theta, d, seed0 + g) for g in range(games)]
    wins = 0.0
    for g, r in enumerate(pool.map(play, jobs, chunksize=4)):
        wins += _win(r["a"], r["b"]) if g % 2 == 0 else _win(r["b"], r["a"])
    return wins / games


def train(args) -> None:
    rng = np.random.default_rng(args.seed)
    if args.resume and (OUT / "design.json").exists():
        st = load()
    else:
        from rl.imitate import clone
        theta = clone(seed=args.seed)
        st = {"theta": theta, "pool": [theta.copy()], "mu": current_design(),
              "sd": np.concatenate([np.full(N_DESIGN - 1, 0.25), [6.0]]), "round": 0}
    OUT.mkdir(exist_ok=True)
    log = open(OUT / "log.csv", "a")
    with mp.Pool(args.workers) as pool:
        for _ in range(args.rounds):
            t0 = time.time()
            rnd = st["round"]
            for k in range(args.agent_iters):
                # Opponents: recent past selves, plus the rule bot (None) so
                # it can't drift into beating only itself.
                opps = st["pool"][-args.pool_size:] + [None]
                st["theta"], fit = es_step(pool, st["theta"], opps, st["mu"], args, rng,
                                           seed0=10_000 * rnd + 100 * k)
            st["pool"].append(st["theta"].copy())
            wr = vs_explorer(pool, st["theta"], st["mu"], 40, seed0=9_000_000 + rnd * 100)
            # Two bad players make every design look "close" — neither
            # scores, so the gap is tiny. The designer only gets a say once
            # the players are at least as good as the rule bot.
            if wr >= args.design_after:
                for k in range(args.design_iters):
                    st["mu"], st["sd"], ev = cem_step(pool, st["theta"], st["mu"], st["sd"], args, rng,
                                                      seed0=5_000_000 + 10_000 * rnd + 100 * k)
            else:
                ev = evaluate_designs(pool, st["theta"], [st["mu"]], args,
                                      seed0=5_000_000 + 10_000 * rnd)[0]
            st["round"] = rnd + 1
            save(st)
            line = (f"{st['round']},{fit:.3f},{wr:.3f},{ev['score']:.2f},{ev['gap']:.2f},"
                    f"{ev['bias']:+.2f},{ev['chal']:.2f},{st['mu'][-1]:.1f}")
            log.write(line + "\n"); log.flush()
            print(f"round {st['round']:>3}  self-play fit {fit:.3f}  vs rule-bot {wr:.0%}  "
                  f"design J {ev['score']:+.2f} (|gap| {ev['gap']:.1f}, bias {ev['bias']:+.1f}, "
                  f"challenges {ev['chal']:.1f})  chips {st['mu'][-1]:.0f}  [{time.time() - t0:.0f}s]",
                  flush=True)


# --- report ----------------------------------------------------------------------

def _fmt(key: str, v: float) -> str:
    if key == "chips_per_unit":
        return f"{v:.1f}" if v < 5 else f"{round(v)}"
    if key == "steal_pct":
        return f"{min(100, round(v))}%"
    return f"{round(v)}"


def report(args) -> None:
    st = load()
    with mp.Pool(args.workers) as pool:
        before, after = evaluate_designs(pool, st["theta"], [current_design(), st["mu"]], args, seed0=77_000_000)
        wr = vs_explorer(pool, st["theta"], st["mu"], 100, seed0=88_000_000)
    print(f"trained for {st['round']} rounds; learned player beats the rule bot {wr:.0%} of games\n")
    print(f"{'':<22}{'|gap|':>8}{'bias':>8}{'challenges':>12}")
    for label, e in (("current seed values", before), ("designer's values", after)):
        print(f"{label:<22}{e['gap']:>8.1f}{e['bias']:>+8.1f}{e['chal']:>12.1f}")
    print(f"\nstarting chips: {round(current_design()[-1])} -> {round(st['mu'][-1])}\n")
    print(f"{'任務':<16}{'now':>8}{'->':>4}{'designer':>10}{'×':>7}")
    for (name, key, base), m in zip(BASE, st["mu"][:-1]):
        flag = "" if abs(m) < 0.1 else ("  ↑" if m > 0 else "  ↓")
        print(f"{name:<16}{_fmt(key, base):>8}{'->':>4}{_fmt(key, base * math.exp(m)):>10}{math.exp(m):>7.2f}{flag}")


def main() -> None:
    ap = argparse.ArgumentParser(description="adversarial RL tuning for Metro Rush")
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--agent-iters", type=int, default=5, help="ES steps per round")
    ap.add_argument("--design-iters", type=int, default=2, help="CEM steps per round")
    ap.add_argument("--pop", type=int, default=40, help="ES population (even)")
    ap.add_argument("--games", type=int, default=16, help="games per ES candidate")
    ap.add_argument("--sigma", type=float, default=0.05)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--decay", type=float, default=0.005, help="weight decay")
    ap.add_argument("--pool-size", type=int, default=5, help="past selves to play against")
    ap.add_argument("--design-pop", type=int, default=24)
    ap.add_argument("--design-games", type=int, default=24)
    ap.add_argument("--min-sd", type=float, default=0.03)
    ap.add_argument("--design-after", type=float, default=0.5,
                    help="designer waits until the player beats the rule bot this often")
    ap.add_argument("--w-gap", type=float, default=1.0)
    ap.add_argument("--w-bias", type=float, default=1.0)
    ap.add_argument("--w-chal", type=float, default=1.0)
    ap.add_argument("--w-reg", type=float, default=10.0)
    ap.add_argument("--workers", type=int, default=max(1, mp.cpu_count() - 1))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.report:
        report(args)
    else:
        train(args)


if __name__ == "__main__":
    main()
