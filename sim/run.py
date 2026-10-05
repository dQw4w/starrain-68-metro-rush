"""CLI for the tuning harness.

    # sanity check the engine with no model at all (fast)
    python run.py --games 20 --agent heuristic

    # one game against a local model, printing every prompt
    python run.py --games 1 --agent llm --model qwen2.5:7b --verbose

    # sweep the starting-chip values you're trying to pick
    python run.py --games 10 --agent heuristic --sweep-start-chips 30,40,50,60
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import HeuristicAgent, LLMAgent  # noqa: E402
from config import SimConfig  # noqa: E402
from engine import Engine  # noqa: E402
from llm import LLMClient, LLMConfig  # noqa: E402
from network import Network  # noqa: E402


def play_one(cfg: SimConfig, agent_kind: str, llm_cfg: LLMConfig, seed: int):
    rng = random.Random(seed)
    net = Network(cfg)
    heuristic = HeuristicAgent(rng)
    if agent_kind == "llm":
        client = LLMClient(llm_cfg)
        agents = {
            name: LLMAgent(client, heuristic, cfg.max_llm_calls_per_team)
            for name in cfg.starting_chips
        }
    else:
        agents = {name: heuristic for name in cfg.starting_chips}
    return Engine(cfg, net, agents, rng).run()


def summarise(results, label: str) -> dict:
    station_gaps = [r.station_gap for r in results]
    chip_gaps = [r.chip_gap for r in results]
    names = list(results[0].teams)
    print(f"\n=== {label} ({len(results)} games) ===")
    for n in names:
        chips = [r.teams[n]["chips"] for r in results]
        stations = [r.teams[n]["stations"] for r in results]
        done = [r.teams[n]["attempted"] for r in results]
        print(f"  {n:<10} 代幣 {statistics.mean(chips):6.1f}  "
              f"車站 {statistics.mean(stations):5.1f}  任務嘗試 {statistics.mean(done):4.1f}")
    print(f"  → 車站差距 平均 {statistics.mean(station_gaps):.2f}"
          f"（中位數 {statistics.median(station_gaps):.1f}, 最大 {max(station_gaps)}）")
    print(f"  → 代幣差距 平均 {statistics.mean(chip_gaps):.2f}"
          f"（中位數 {statistics.median(chip_gaps):.1f}, 最大 {max(chip_gaps)}）")
    return {
        "station_gap": statistics.mean(station_gaps),
        "chip_gap": statistics.mean(chip_gaps),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Metro Rush parameter-tuning simulator")
    ap.add_argument("--games", type=int, default=10)
    ap.add_argument("--agent", choices=["heuristic", "llm"], default="heuristic")
    ap.add_argument("--minutes", type=int, default=None, help="override game length")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--base-url", default="http://localhost:11434/v1",
                    help="ollama http://localhost:11434/v1 | lm studio http://localhost:1234/v1")
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--verbose", action="store_true", help="print every prompt and reply")
    ap.add_argument("--transcript", action="store_true", help="print the game log")
    ap.add_argument("--max-llm-calls", type=int, default=0,
                    help="per team per game; 0 = unlimited. Keeps slow models bounded.")
    ap.add_argument("--sweep-start-chips", default=None,
                    help="comma-separated values to try for BOTH teams' starting chips")
    args = ap.parse_args()

    llm_cfg = LLMConfig(base_url=args.base_url, model=args.model,
                        temperature=args.temperature, verbose=args.verbose)

    def make_cfg(start_chips: int | None = None) -> SimConfig:
        cfg = SimConfig()
        if args.minutes:
            cfg.game_minutes = args.minutes
        cfg.max_llm_calls_per_team = args.max_llm_calls
        if start_chips is not None:
            cfg.starting_chips = {k: start_chips for k in cfg.starting_chips}
        return cfg

    if args.sweep_start_chips:
        rows = []
        for value in [int(v) for v in args.sweep_start_chips.split(",")]:
            cfg = make_cfg(value)
            results = [play_one(cfg, args.agent, llm_cfg, args.seed + i) for i in range(args.games)]
            stats = summarise(results, f"starting_chips={value}")
            rows.append((value, stats))
        print("\n=== sweep summary (smaller gap = more even game) ===")
        for value, s in sorted(rows, key=lambda r: (r[1]["station_gap"], r[1]["chip_gap"])):
            print(f"  starting_chips={value:<4} 車站差距 {s['station_gap']:.2f}  代幣差距 {s['chip_gap']:.2f}")
        return

    cfg = make_cfg()
    results = []
    for i in range(args.games):
        r = play_one(cfg, args.agent, llm_cfg, args.seed + i)
        results.append(r)
        if args.transcript:
            print(f"\n----- game {i} -----")
            print("\n".join(r.transcript))
    summarise(results, f"{args.agent} agent")


if __name__ == "__main__":
    main()
