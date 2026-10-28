"""Reward balance: what each challenge actually pays per minute spent on it.

The question this answers is "which rewards are out of line with each other",
which you can't eyeball from seed_challenges.py because a fixed 80 and a
call-your-shot at 5/unit aren't comparable until you fold in the success
rate, the best call, and how long the thing takes.

    python3 balance.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from challenges import profile_for  # noqa: E402
from config import SimConfig  # noqa: E402
from fairness import travel_times  # noqa: E402
from network import Network  # noqa: E402


# Steal and multiplier pay a percentage of somebody's balance, so their value
# depends entirely on what balances actually look like in play. Measured over
# 20 simulated games (explorer agent, 25 starting chips):
#
#   minute   0    60   120   180   240   300   360
#   median  24    36    30    10     8     4     2
#   p75     24    43    75    42    38    24    34
#
# The median collapses because teams spend everything on stations. But a team
# choosing *when* to steal doesn't face the median — they can wait for the
# opponent to be flush, so the 75th percentile mid-game is the fairer
# reference. Both are shown below, because the spread is the whole story.
TYPICAL_BALANCE = 20             # median across a game
POOR_BALANCE = 10                # what you have when you go looking for a challenge
RICH_BALANCE = 70                # a well-timed strike, mid-game p75


# Chips aren't the score — stations are, and chips are only the fuel for
# claiming them. So the worth of any chip-denominated reward is "how many more
# stations does this let me claim", and that collapses as you get richer:
# past ~20 chips the binding constraint stops being money and becomes the
# clock, because you can only physically reach ~30 stations in a day.
#
# Measured by running the sim with different starting chips and reading off the
# slope (24 games each, explorer agent):
#
#   balance    10     20     30     40     60     80
#   stations  22.7   28.0   29.0   29.5   32.1   32.9
#   per chip         0.53   0.10   0.05   0.13   0.04
#
# Crude and noisy past 30, but the shape — roughly 0.5 when broke, ~0.1 when
# comfortable — is the part that matters.
_MARGINAL = [(0, 0.60), (10, 0.53), (20, 0.10), (30, 0.05), (60, 0.10), (80, 0.04), (200, 0.03)]


def stations_per_chip(balance: float) -> float:
    for (b0, v0), (b1, v1) in zip(_MARGINAL, _MARGINAL[1:]):
        if balance <= b1:
            f = (balance - b0) / (b1 - b0) if b1 > b0 else 0
            return v0 + f * (v1 - v0)
    return _MARGINAL[-1][1]


def chips_to_stations(chips: float, balance: float) -> float:
    """Rough stations bought by `chips` arriving on top of `balance`."""
    return chips * stations_per_chip(balance)


def analyse(ch, prof):
    rc = ch.reward_config
    if ch.type == "fixed":
        return rc.get("chips", 0) * prof.success, prof.success, f"{rc.get('chips')} 固定"
    if ch.type == "variable":
        lo, hi = prof.call_range or (1, 1)
        per = rc.get("chips_per_unit", 0)
        best_n, best_ev, best_p = lo, 0.0, 0.0
        for n in range(lo, hi + 1):
            p = prof.success_prob(n)
            if n * per * p > best_ev:
                best_n, best_ev, best_p = n, n * per * p, p
        return best_ev, best_p, f"{per}/單位，最佳喊 {best_n}（p={best_p:.2f}）"
    if ch.type == "steal":
        pct = rc.get("steal_pct", 0) / 100
        typical = TYPICAL_BALANCE * pct * prof.success
        rich = RICH_BALANCE * pct * prof.success
        return typical, prof.success, f"偷 {rc.get('steal_pct')}%｜抓到肥羊 {rich:.0f} 枚"
    pct = rc.get("multiplier_pct", 0) / 100
    typical = TYPICAL_BALANCE * pct * prof.success
    rich = RICH_BALANCE * pct * prof.success
    return typical, prof.success, f"+{rc.get('multiplier_pct')}%｜自己很有錢時 {rich:.0f} 枚"


def detour_minutes(net: Network, cfg: SimConfig) -> tuple[dict[str, float], float]:
    """How much going out of your way to each station really costs.

    Distance from 台北車站 is the wrong yardstick: teams aren't at 台北車站,
    and a stop two stations off a trunk line can still be miserable to reach
    if the only way in is a sparse branch shuttle. What a detour costs is:
    you're at some station A heading for some B, and you stop at T instead,
    so you lose d(A,T) + d(T,B) - d(A,B). Averaged over every A and B that's

        2 * (mean minutes from anywhere to T) - (mean trip length)

    which is small for a stop that's on the way to everything and large for
    a dead end, whatever its straight-line distance."""
    stations = net.all_stations
    tt = {a: travel_times(net, cfg, a) for a in stations}
    mean_trip = sum(tt[a].get(b, 0) for a in stations for b in stations) / len(stations) ** 2
    to = {t: sum(tt[a].get(t, 0) for a in stations) / len(stations) for t in stations}
    return {t: 2 * to[t] - mean_trip for t in stations}, mean_trip


def main() -> None:
    cfg = SimConfig()
    net = Network(cfg)
    detour, mean_trip = detour_minutes(net, cfg)
    rows = []
    for ch in net.challenges:
        prof = profile_for(ch.name)
        ev, p, desc = analyse(ch, prof)
        mins = prof.mean_minutes
        # A team doing a challenge is usually doing it *because* it's short of
        # chips, so price the gain against a poor balance.
        gain_st = chips_to_stations(ev, POOR_BALANCE)
        if ch.type == "steal":
            # Zero-sum, but the two sides are worth wildly different amounts:
            # what you gain is priced at your (poor) balance, what they lose at
            # theirs. Taking 20 chips off a team sitting on 70 barely dents
            # them; the value is nearly all on your side.
            pct = ch.reward_config.get("steal_pct", 0) / 100
            moved = RICH_BALANCE * pct * prof.success
            denied_st = chips_to_stations(moved, RICH_BALANCE)
            gap_st = chips_to_stations(moved, POOR_BALANCE) + denied_st
        else:
            gap_st = gain_st
        stn, walk = net.nearest_station_to(ch)
        # Walking out from the station and back is pure detour too.
        center = detour[stn] + 2 * walk
        total = center + mins
        rows.append((center, ev, mins, p, ch.name, ch.type, desc, gap_st, total))
    rows.sort()
    print(f"{'任務':<20}{'型別':<11}{'繞路分':>8}{'總耗時':>7}{'期望枚':>7}{'≈車站':>7}"
          f"{'站/10分':>8}  獎勵設定")
    print("-" * 112)
    for center, ev, mins, p, name, typ, desc, gap_st, total in rows:
        print(f"{name:<20}{typ:<11}{center:>8.0f}{total:>7.0f}{ev:>7.0f}{gap_st:>7.1f}"
              f"{gap_st / total * 10:>8.2f}  {desc}")
    print("-" * 112)
    print(f"繞路分 = 從隨機一站要去另一個隨機站時，順路繞去做這個任務平均多花的分鐘數"
          f"（含班次稀疏支線的候車、出站走路來回）；平均一趟車程 {mean_trip:.0f} 分。")
    print(f"總耗時 = 繞路分 ＋ 現場時間。按繞路分排序。")
    print(f"「≈車站」= 這個任務大約值幾座車站的分差，已折算代幣的邊際價值。")
    print(f"偷竊額外計入對手的損失，但那部分按『對手有 {RICH_BALANCE} 枚』折算，"
          f"而有錢人的代幣邊際價值低（{stations_per_chip(RICH_BALANCE):.2f} 站/枚），"
          f"所以價值幾乎都在自己這邊。")



if __name__ == "__main__":
    main()
