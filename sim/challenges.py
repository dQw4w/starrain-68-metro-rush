"""How long each challenge takes and how likely it is to be passed.

The LLM never plays a challenge — it only decides whether to walk to one and,
for call-your-shot, what number to call. The outcome is then rolled from the
profile here. So these numbers ARE the model of the challenge: if a profile
is wrong, the tuning it produces is wrong.

Everything is a guess until you time the real thing. The duration figures
come from the time limits written into each task (plus setup/argument time);
the success curves are judgement calls. Treat them as the second thing to
tune after rewards.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable


@dataclass
class ChallengeProfile:
    #: Mean minutes on site, including faffing about and the admin judging.
    mean_minutes: float
    #: Spread; 0 for a hard time-boxed task that always takes the same slot.
    sd_minutes: float = 0.0
    #: Pass rate for fixed/steal/multiplier challenges.
    success: float = 0.7
    #: Call-your-shot only: legal range for the number the team calls.
    call_range: tuple[int, int] | None = None
    #: Call-your-shot only: pass rate as a function of what they called.
    success_fn: Callable[[int], float] | None = None

    def sample_minutes(self, rng: random.Random) -> int:
        if self.sd_minutes <= 0:
            return max(1, round(self.mean_minutes))
        return max(1, round(rng.gauss(self.mean_minutes, self.sd_minutes)))

    def success_prob(self, called: int | None) -> float:
        if self.success_fn is not None and called is not None:
            return max(0.0, min(1.0, self.success_fn(called)))
        return max(0.0, min(1.0, self.success))


def _decay(base: float, per_unit: float, floor: float = 0.02):
    """p(n) = base * per_unit^(n-1): `base` is the pass rate for calling 1,
    and each extra unit multiplies by `per_unit`.

    Anchored at n=1, not n=0 — calling the minimum should give you `base`.
    (It used to decay from 0, which quietly turned a "nearly free" 0.97 base
    into a 0.53 coin flip at n=1 and made every call-your-shot look far
    harder than intended.)"""
    def f(n: int, _b=base, _p=per_unit, _f=floor) -> float:
        return max(_f, _b * (_p ** max(0, n - 1)))
    return f


def _beats_the_clock(minutes_per_unit: float, limit: float, spread: float = 1.2,
                      ceiling: float = 0.97, floor: float = 0.02):
    """For a task that's purely 'can you fit n repetitions into a time limit'.

    p(n) is a logistic on the slack left over (limit - n * minutes_per_unit),
    so it's flat while there's room, falls off a cliff right where the clock
    runs out, and bottoms out past it. A geometric decay can't express that
    shape — it makes 'obviously impossible' look merely unlikely.
    """
    def f(n: int) -> float:
        slack = limit - n * minutes_per_unit
        p = 1 / (1 + math.exp(-slack / spread))
        return max(floor, min(ceiling, p))
    return f


# Keyed by the challenge `name` in backend/seed_challenges.py. A challenge
# with no entry here falls back to DEFAULT_PROFILE, so adding a task to the
# seed file won't break a sim run — it'll just be modelled crudely.
PROFILES: dict[str, ChallengeProfile] = {
    # 10-minute hunt upstairs + the admin reading out 7 clubs.
    "台大二活任務": ChallengeProfile(mean_minutes=16, sd_minutes=3, success=0.55),
    # Trawling Ximending shops for a specific character's merch under 300.
    "西門町任務": ChallengeProfile(mean_minutes=25, sd_minutes=8, success=0.5),
    # Counting 1..N with claps on 6/8 multiples. Long calls are brutal.
    "仁愛圓環任務": ChallengeProfile(
        mean_minutes=10, sd_minutes=3,
        call_range=(30, 100),
        # ~85% at 30, falling off steeply; 100 is close to hopeless.
        success_fn=lambda n: max(0.03, 0.85 * (0.975 ** (n - 30))),
    ),
    # Pacing out the underground mall with no phone.
    "台北地下街任務": ChallengeProfile(mean_minutes=22, sd_minutes=6, success=0.45),
    # One guess at the right brunch shop near 葫洲.
    "葫洲站任務": ChallengeProfile(mean_minutes=12, sd_minutes=4, success=0.5),
    # Relay up the Miramar stairs in 10 minutes: one leg per person, nobody
    # twice, order fixed up front.
    #
    # call_range's ceiling IS the team's headcount — one leg each means they
    # can never call more than that, so set it to your real team size. It
    # also caps this challenge's payout at headcount x chips_per_unit, which
    # is the single biggest reward in the game at 6 people (300 chips).
    "美麗華任務": ChallengeProfile(
        mean_minutes=16, sd_minutes=3,
        call_range=(1, 6),
        # The wheel is on 5F, so a leg is four floors up and four down —
        # about 2 minutes at a normal pace including the handover. Against a
        # 10-minute limit that puts the cliff at 5 legs: 4 is comfortable, 5
        # is a coin flip, 6 means everyone sprints and someone gasses out.
        success_fn=_beats_the_clock(minutes_per_unit=2.0, limit=10.0),
    ),
    # DDR: clear a self-declared difficulty level on a 星/雨/star/rain song.
    "明曜百貨任務": ChallengeProfile(
        mean_minutes=20, sd_minutes=5,
        call_range=(1, 15),
        # Comfortable to ~5, a real wall past 10 for non-players.
        success_fn=lambda n: max(0.03, 0.95 * (0.78 ** max(0, n - 3))),
    ),
    # Guess the 三鶯線 countdown within a minute.
    "頂埔站任務": ChallengeProfile(mean_minutes=10, sd_minutes=3, success=0.35),
    # Morse by clapping, whole word must be right.
    "南港區民活動中心任務": ChallengeProfile(mean_minutes=18, sd_minutes=5, success=0.4),
    # Film a full take-off from the observation deck — mostly waiting.
    "松山機場任務": ChallengeProfile(mean_minutes=20, sd_minutes=8, success=0.75),
    # Guess the next train type in/out of the depot; retries allowed, so it's
    # slow but nearly certain.
    "木柵機廠任務": ChallengeProfile(mean_minutes=25, sd_minutes=10, success=0.9),
    # 7 of 10 ping-pong free throws.
    "辛亥國小任務": ChallengeProfile(mean_minutes=15, sd_minutes=4, success=0.35),
    # Memorise the inscription, find it inside in 10 minutes.
    "林本源園邸任務": ChallengeProfile(mean_minutes=18, sd_minutes=4, success=0.6),
    # Find n 幸福-signed food shops in 10 minutes, no phone.
    "幸福站任務": ChallengeProfile(
        mean_minutes=14, sd_minutes=3,
        call_range=(1, 8),
        success_fn=_decay(0.95, 0.62),
    ),
}

DEFAULT_PROFILE = ChallengeProfile(mean_minutes=18, sd_minutes=5, success=0.5)


def profile_for(name: str) -> ChallengeProfile:
    return PROFILES.get(name, DEFAULT_PROFILE)
