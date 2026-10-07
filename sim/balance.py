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
from network import Network  # noqa: E402

ASSUMED_OPPONENT_CHIPS = 60      # steal/multiplier scale off a balance


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
        gain = ASSUMED_OPPONENT_CHIPS * rc.get("steal_pct", 0) / 100
        return gain * prof.success, prof.success, f"偷 {rc.get('steal_pct')}%（假設對手 {ASSUMED_OPPONENT_CHIPS} 枚）"
    gain = ASSUMED_OPPONENT_CHIPS * rc.get("multiplier_pct", 0) / 100
    return gain * prof.success, prof.success, f"+{rc.get('multiplier_pct')}%（假設自己 {ASSUMED_OPPONENT_CHIPS} 枚）"


def main() -> None:
    net = Network(SimConfig())
    rows = []
    for ch in net.challenges:
        prof = profile_for(ch.name)
        ev, p, desc = analyse(ch, prof)
        mins = prof.mean_minutes
        rows.append((ev / mins, ev, mins, p, ch.name, ch.type, desc))
    rows.sort(reverse=True)
    print(f"{'任務':<22}{'型別':<11}{'期望枚':>7}{'現場分':>7}{'枚/分':>7}  獎勵設定")
    print("-" * 96)
    for per_min, ev, mins, p, name, typ, desc in rows:
        print(f"{name:<22}{typ:<11}{ev:>7.0f}{mins:>7.0f}{per_min:>7.1f}  {desc}")
    vals = [r[0] for r in rows]
    print("-" * 96)
    print(f"枚/分 中位數 {sorted(vals)[len(vals)//2]:.1f}，最高 {max(vals):.1f}，最低 {min(vals):.1f}")
    print("（現場分不含交通時間，所以這是『到了之後』的效率，不是整體划算程度）")


if __name__ == "__main__":
    main()
