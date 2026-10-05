"""The metro network and walking distances, read straight out of the real
seed data so the simulation can't drift from the deployed game.

`backend/seed_stations.py` and `seed_challenges.py` are plain data modules —
they only touch the DB from inside `seed()`, so importing them here costs
nothing and needs no database.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import seed_challenges  # noqa: E402
import seed_stations  # noqa: E402

from config import CROSS_PLATFORM_TRANSFERS, SimConfig  # noqa: E402


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1 = a
    lat2, lng2 = b
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


@dataclass(frozen=True)
class ChallengeSite:
    name: str
    type: str
    reward_config: dict
    location_name: str
    lat: float
    lng: float


class Network:
    """Station order per line, plus the lookups the engine needs."""

    def __init__(self, cfg: SimConfig):
        self.cfg = cfg
        self.line_stations: dict[str, list[str]] = dict(seed_stations._LINE_STATIONS)
        self.coords: dict[str, tuple[float, float]] = dict(seed_stations._COORDS)
        self.line_names = {code: zh for code, zh, _en, _c, _s in seed_stations.LINES}

        self.lines_at: dict[str, list[str]] = {}
        for code, names in self.line_stations.items():
            for n in names:
                self.lines_at.setdefault(n, []).append(code)

        self.challenges: list[ChallengeSite] = []
        for name, ctype, reward, location_name, lat, lng, _state in seed_challenges._CHALLENGES:
            lat, lng = seed_challenges._COORD_OVERRIDES.get(name, (lat, lng))
            merged = {**reward, **cfg.challenge_reward_overrides.get(name, {})}
            self.challenges.append(
                ChallengeSite(name, ctype, merged, location_name or name, lat, lng)
            )

    # --- stations ----------------------------------------------------------

    @property
    def all_stations(self) -> list[str]:
        return sorted(self.lines_at)

    def neighbour(self, station: str, line: str, direction: int) -> str | None:
        """Next station along `line`; direction +1 runs toward the end of the
        ordered list in seed_stations.py, -1 toward its start."""
        order = self.line_stations.get(line)
        if not order or station not in order:
            return None
        i = order.index(station) + direction
        return order[i] if 0 <= i < len(order) else None

    def terminus(self, line: str, direction: int) -> str:
        order = self.line_stations[line]
        return order[-1] if direction > 0 else order[0]

    def ride_options(self, station: str) -> list[tuple[str, int, str]]:
        """(line_code, direction, next_station) for every train you could board."""
        out = []
        for line in self.lines_at.get(station, []):
            for direction in (1, -1):
                nxt = self.neighbour(station, line, direction)
                if nxt is not None:
                    out.append((line, direction, nxt))
        return out

    # --- time ---------------------------------------------------------------

    def walk_minutes(self, frm: tuple[float, float], to: tuple[float, float]) -> int:
        metres = haversine_m(frm, to) * self.cfg.walk_detour_factor
        return max(1, round(metres / self.cfg.walk_speed_m_per_min))

    def walk_minutes_station_to_challenge(self, station: str, ch: ChallengeSite) -> int:
        return self.walk_minutes(self.coords[station], (ch.lat, ch.lng))

    def board_cost(self, station: str, from_line: str | None, to_line: str) -> int:
        """Minutes from standing on the concourse to the train pulling out:
        a wait, plus the walk between platforms when it's a real transfer."""
        cfg = self.cfg
        if from_line is None or from_line == to_line:
            return cfg.wait_minutes
        if station in CROSS_PLATFORM_TRANSFERS:
            # Same platform — just wait for the other line's train.
            return cfg.transfer_wait_minutes
        return cfg.transfer_walk_minutes + cfg.transfer_wait_minutes

    def nearest_challenges(
        self, station: str, available: set[str], limit: int
    ) -> list[tuple[ChallengeSite, int]]:
        scored = [
            (ch, self.walk_minutes_station_to_challenge(station, ch))
            for ch in self.challenges
            if ch.name in available
        ]
        scored = [(c, m) for c, m in scored if m <= self.cfg.max_walk_minutes]
        scored.sort(key=lambda t: t[1])
        return scored[:limit]
