"""Which pairs of start stations give the two teams an even game?

Answers it from the network rather than from intuition: a proper
shortest-travel-time search (riding, waiting, transferring — with the
cross-platform exceptions) out of every station, then for each candidate
pair, how similar the two teams' opportunities actually are.

    python3 fairness.py                    # best pairs overall
    python3 fairness.py --fixed 公館        # best partner for 公館
    python3 fairney.py --profile 公館 科技大樓   # side-by-side on two stations
"""
from __future__ import annotations

import argparse
import heapq
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from challenges import profile_for  # noqa: E402
from config import CROSS_PLATFORM_TRANSFERS, SimConfig  # noqa: E402
from network import Network  # noqa: E402


def travel_times(net: Network, cfg: SimConfig, origin: str) -> dict[str, int]:
    """Minutes from standing on `origin`'s concourse to arriving at every
    other station. Node is (station, line you're aboard) so transfers get
    charged properly."""
    dist: dict[tuple[str, str], int] = {}
    pq: list[tuple[int, str, str]] = []
    for line in net.lines_at.get(origin, []):
        # Boarding anything from a standstill costs one wait.
        heapq.heappush(pq, (cfg.wait_minutes, origin, line))
    best: dict[str, int] = {origin: 0}

    while pq:
        t, station, line = heapq.heappop(pq)
        if dist.get((station, line), 10**9) <= t:
            continue
        dist[(station, line)] = t
        if t < best.get(station, 10**9):
            best[station] = t
        # ride one stop either way
        for direction in (1, -1):
            nxt = net.neighbour(station, line, direction)
            if nxt is None:
                continue
            nt = t + cfg.minutes_per_segment
            if nt < dist.get((nxt, line), 10**9):
                heapq.heappush(pq, (nt, nxt, line))
        # change lines here
        for other in net.lines_at.get(station, []):
            if other == line:
                continue
            pen = (cfg.transfer_wait_minutes if station in CROSS_PLATFORM_TRANSFERS
                   else cfg.transfer_walk_minutes + cfg.transfer_wait_minutes)
            nt = t + pen
            if nt < dist.get((station, other), 10**9):
                heapq.heappush(pq, (nt, station, other))
    return best


def _expected_reward(name: str, ch) -> float:
    """Chips a competent team should expect out of this challenge."""
    rc = ch.reward_config
    prof = profile_for(name)
    if ch.type == "fixed":
        return rc.get("chips", 0) * prof.success
    if ch.type == "variable":
        lo, hi = prof.call_range or (1, 1)
        per = rc.get("chips_per_unit", 0)
        # The call they'd actually pick: the one maximising expected value.
        return max(n * per * prof.success_prob(n) for n in range(lo, hi + 1))
    return 25 * prof.success        # steal/multiplier depend on balances


@dataclass
class StationProfile:
    station: str
    lines: int
    #: Mean minutes to reach every station — how central you are for claiming.
    mean_station_time: float
    #: Minutes to get to each challenge (ride + walk from its best drop-off).
    challenge_times: dict[str, int]

    @property
    def nearest_3_challenges(self) -> float:
        vals = sorted(self.challenge_times.values())[:3]
        return sum(vals) / len(vals) if vals else 999.0

    @property
    def discounted_challenge_value(self) -> float:
        """Expected chips available, each discounted by how long it takes to
        get there. Everything in Taipei is within an hour, so a plain
        within-60-min total is identical for every station and tells you
        nothing — the travel cost is the whole story."""
        total = 0.0
        for name, t in self.challenge_times.items():
            ch = next(c for c in CHALLENGES if c.name == name)
            total += _expected_reward(name, ch) / (1 + t / 30)
        return total


CHALLENGES = []     # filled in by build_profiles


def build_profiles(net: Network, cfg: SimConfig) -> dict[str, StationProfile]:
    global CHALLENGES
    CHALLENGES = net.challenges
    drop_offs = {c.name: net.nearest_station_to(c) for c in net.challenges}
    out: dict[str, StationProfile] = {}
    for station in net.all_stations:
        tt = travel_times(net, cfg, station)
        ctimes = {}
        for ch in net.challenges:
            stn, walk = drop_offs[ch.name]
            ride = tt.get(stn)
            if ride is None:
                continue
            ctimes[ch.name] = ride + walk
        out[station] = StationProfile(
            station=station,
            lines=len(net.lines_at.get(station, [])),
            mean_station_time=sum(tt.values()) / len(tt),
            challenge_times=ctimes,
        )
    return out


SEPARATION: dict[tuple[str, str], int] = {}


def pair_asymmetry(a: StationProfile, b: StationProfile) -> dict:
    """How lopsided a game starting from these two would be. Lower = fairer."""
    reach = abs(a.mean_station_time - b.mean_station_time)
    chal = abs(a.nearest_3_challenges - b.nearest_3_challenges)
    value = abs(a.discounted_challenge_value - b.discounted_challenge_value)
    # Also: do they overlap? Two starts on top of each other means one
    # contested pile instead of two halves of a city.
    overlap = sum(
        1 for name in a.challenge_times
        if abs(a.challenge_times[name] - b.challenge_times.get(name, 999)) <= 5
    )
    # Weights: being equally central matters, but equal access to the
    # earning opportunities matters more — that's where the big swings are.
    score = reach / 3 + chal / 2 + value / 8
    return {
        "separation": SEPARATION.get((a.station, b.station), -1),
        "reach_diff": round(reach, 1),
        "chal_time_diff": round(chal, 1),
        "chal_value_diff": round(value, 1),
        "shared_challenges": overlap,
        "score": round(score, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Start-station fairness analysis")
    ap.add_argument("--fixed", default=None, help="hold one team at this station, rank partners")
    ap.add_argument("--profile", nargs="*", default=None, help="dump these stations' profiles")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--min-lines", type=int, default=1,
                    help="only consider interchanges with at least this many lines")
    ap.add_argument("--min-separation", type=int, default=0,
                    help="minutes the two starts must be apart. Two starts on top of "
                         "each other score 'fair' but just make both teams race for "
                         "the same stations instead of each having a region.")
    args = ap.parse_args()

    cfg = SimConfig()
    net = Network(cfg)
    profiles = build_profiles(net, cfg)
    for st in net.all_stations:
        for other, t in travel_times(net, cfg, st).items():
            SEPARATION[(st, other)] = t

    if args.profile:
        for name in args.profile:
            p = profiles.get(name)
            if p is None:
                print(f"{name}: 不存在")
                continue
            print(f"\n=== {p.station} ===")
            print(f"  路線數：{p.lines}")
            print(f"  平均抵達全網車站：{p.mean_station_time:.1f} 分鐘（越小越中心）")
            print(f"  最近 3 個任務平均 {p.nearest_3_challenges:.1f} 分鐘")
            print(f"  任務價值（按路程折現）：{p.discounted_challenge_value:.0f}")
            print("  各任務抵達時間（分）：")
            for n, t in sorted(p.challenge_times.items(), key=lambda kv: kv[1]):
                print(f"    {t:>4}　{n}")
        return

    candidates = [p for p in profiles.values() if p.lines >= args.min_lines]
    rows = []
    if args.fixed:
        anchor = profiles.get(args.fixed)
        if anchor is None:
            print(f"找不到車站：{args.fixed}")
            return
        for p in candidates:
            if p.station == anchor.station:
                continue
            rows.append((anchor.station, p.station, pair_asymmetry(anchor, p)))
        title = f"與「{args.fixed}」搭配最公平的車站"
    else:
        for i, a in enumerate(candidates):
            for b in candidates[i + 1:]:
                rows.append((a.station, b.station, pair_asymmetry(a, b)))
        title = "最公平的起點組合"

    if args.min_separation:
        rows = [r for r in rows if r[2]["separation"] >= args.min_separation]
    rows.sort(key=lambda r: r[2]["score"])
    print(f"\n=== {title}（score 越小越公平）===")
    print(f"{'A':<10}{'B':<10}{'score':>7}{'相隔分':>7}{'中心度差':>9}{'任務時間差':>10}{'任務價值差':>10}{'共用任務':>8}")
    for a, b, m in rows[: args.top]:
        print(f"{a:<10}{b:<10}{m['score']:>7.2f}{m['separation']:>7}{m['reach_diff']:>9.1f}"
              f"{m['chal_time_diff']:>10.1f}{m['chal_value_diff']:>10.1f}{m['shared_challenges']:>8}")


if __name__ == "__main__":
    main()
