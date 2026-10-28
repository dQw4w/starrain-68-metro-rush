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


def _binomial_at_least(trials: int, p: float, k: int) -> float:
    """P(at least k successes in `trials` independent tries) — for a quiz
    where you call how many questions you'll get right."""
    return sum(
        math.comb(trials, i) * p ** i * (1 - p) ** (trials - i)
        for i in range(k, trials + 1)
    )


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


def _poisson_at_least(mean: float, k: int) -> float:
    """P(at least k finds) when finds turn up at random at an average of
    `mean` per attempt — for "find n of X in 10 minutes" hunts."""
    return 1 - sum(math.exp(-mean) * mean ** i / math.factorial(i) for i in range(k))


def _normal_sf(x: float, mean: float, sd: float) -> float:
    """P(X >= x) for a normal X."""
    return 0.5 * math.erfc((x - mean) / (sd * math.sqrt(2)))


def _best_of_team_hang(team_size: int = 3):
    """Dead hang where the team sends its strongest member. Each member's
    hang time is normal by sex (organiser's figures: men ~30-60s typical,
    women ~15-40s), sex a coin flip, and the call succeeds if the best of the
    team lasts that long. The team doesn't know its exact best time, which is
    what makes calling high a gamble."""
    def f(n: int) -> float:
        one = 0.5 * _normal_sf(n, 45, 15) + 0.5 * _normal_sf(n, 27, 10)
        return 1 - (1 - one) ** team_size
    return f


def _stair_relay(team_size: int, leg_minutes: float = 0.95,
                 fatigue: float = 0.12, limit: float = 10.0, cv: float = 0.10):
    """Rotating stair relay: n legs, runners in a fixed loop. A fresh
    fast-walk leg (four floors up and down, organiser's 35-55s) plus the
    handover is ~0.95 min; each lap a runner has already done makes their
    next leg `fatigue` slower. Total time is treated as normal with a 10%
    spread, and p(n) is the chance it fits under the limit. With 3 runners:
    8 legs ~95%, 9 ~67%, 10 ~21%."""
    def f(n: int) -> float:
        total = sum(leg_minutes * (1 + fatigue * (i // team_size)) for i in range(n))
        return min(0.95, 1 - _normal_sf(limit, total, cv * total))
    return f


# Keyed by the challenge `name` in backend/seed_challenges.py. A challenge
# with no entry here falls back to DEFAULT_PROFILE, so adding a task to the
# seed file won't break a sim run — it'll just be modelled crudely.
PROFILES: dict[str, ChallengeProfile] = {
    # 10-minute hunt upstairs + the admin reading out 7 clubs.
    "台大二活任務": ChallengeProfile(mean_minutes=16, sd_minutes=3, success=0.55),
    # Trawling Ximending shops for a specific character's merch under 300.
    "西門町任務": ChallengeProfile(mean_minutes=25, sd_minutes=8, success=0.9),
    # Counting 1..N with claps on 6/8 multiples. A flat per-number slip rate,
    # set so reaching 80 is the organiser's 40%: 1 - 0.4^(1/80) ≈ 1.14%.
    "建成圓環任務": ChallengeProfile(
        mean_minutes=10, sd_minutes=3,
        call_range=(30, 100),
        success_fn=lambda n: 0.4 ** (n / 80),
    ),
    # Pacing out the underground mall with no phone.
    "台北地下街任務": ChallengeProfile(mean_minutes=22, sd_minutes=6, success=0.45),
    # One guess at the right brunch shop near 葫洲.
    "葫洲站任務": ChallengeProfile(mean_minutes=12, sd_minutes=4, success=0.8),
    # Relay up the Miramar stairs in 10 minutes, in a fixed rotation that
    # loops back to the first runner, so the call isn't capped by headcount.
    "美麗華任務": ChallengeProfile(
        mean_minutes=14, sd_minutes=2,
        call_range=(1, 15),
        success_fn=_stair_relay(team_size=3),
    ),
    # DDR: clear a self-declared difficulty level on a 星/雨/star/rain song.
    "明曜百貨任務": ChallengeProfile(
        mean_minutes=20, sd_minutes=5,
        call_range=(1, 15),
        # Organiser: 1-4 a near-certain pass, the drop is 5-8, 9+ essentially
        # impossible for people who've never played — though splitting the
        # arrows one per person might stretch a team to 10. Logistic centred
        # between 6 and 7: ~95% at 4, ~43% at 7, ~8% at 9, ~3% at 10.
        success_fn=lambda n: max(0.01, min(0.97, 1 / (1 + math.exp((n - 6.75) / 0.9)))),
    ),
    # Guess the 三鶯線 countdown within a minute. Phones are allowed, so a
    # team that thinks to look up the timetable nails it (~95%). One that
    # doesn't is guessing blind: weekend headway is 8 min, countdown uniform
    # over 0-8, and a ±1 min window covers 2 of those 8 minutes (25%).
    # Assume half the teams think of it: 0.5*0.95 + 0.5*0.25 = 0.6.
    "頂埔站任務": ChallengeProfile(mean_minutes=10, sd_minutes=3, success=0.6),
    # Morse by clapping, whole word must be right.
    "南港區民活動中心任務": ChallengeProfile(mean_minutes=18, sd_minutes=5, success=0.65),
    # Film a full take-off from the observation deck — mostly waiting.
    "松山機場任務": ChallengeProfile(mean_minutes=20, sd_minutes=8, success=0.98),
    # Guess the next train type in/out of the depot; retries allowed, so it's
    # slow but nearly certain.
    "木柵機廠任務": ChallengeProfile(mean_minutes=25, sd_minutes=10, success=0.9),
    # 7 of 10 ping-pong free throws.
    "辛亥國小任務": ChallengeProfile(mean_minutes=15, sd_minutes=4, success=0.35),
    # Memorise the inscription, find it inside in 10 minutes.
    "林本源園邸任務": ChallengeProfile(mean_minutes=18, sd_minutes=4, success=0.8),
    # Find n 幸福-signed food shops in 10 minutes, no phone. Nobody knows how
    # many exist near the station; a gut-feel 2.5 found on average, so 1 is
    # ~92%, 2 ~71%, 3 ~46%, 4 ~24%.
    "幸福站任務": ChallengeProfile(
        mean_minutes=14, sd_minutes=3,
        call_range=(1, 8),
        success_fn=lambda n: _poisson_at_least(2.5, n),
    ),
    # Find 世界豆漿大王 without a phone — but asking passers-by is allowed,
    # and it's a famous shop a few minutes from the exit. Hard to fail.
    "頂溪站任務": ChallengeProfile(mean_minutes=14, sd_minutes=5, success=0.85),
    # Get everyone horizontal on an IKEA bed or sofa at the same moment. The
    # task itself is nearly free; what it costs is the trek to the end of the
    # 小碧潭 spur. "Simultaneously" adds a little risk — a whole team lying
    # down at once is the thing staff are most likely to object to.
    "小碧潭任務": ChallengeProfile(mean_minutes=15, sd_minutes=4, success=0.99),
    # Study an installation with no idea what you'll be asked, then answer
    # three detail questions (a count, two missing numbers, a colour
    # ranking) with your backs to it. All three must be right.
    "圓山花博公園任務": ChallengeProfile(mean_minutes=18, sd_minutes=5, success=0.3),
    # Find n claw machines already at >= half their guaranteed-win amount, in
    # 10 minutes, each shop entered once. Organiser's estimate is ~90s per
    # qualifying machine, so finds arrive at random averaging 10/1.5 ≈ 6.7
    # in the window: 4 is ~88%, 6 ~64%, 8 ~33%.
    "饒河夜市任務": ChallengeProfile(
        mean_minutes=14, sd_minutes=2,
        call_range=(1, 10),
        success_fn=lambda n: _poisson_at_least(10 / 1.5, n),
    ),
    # Borrow any book with 溫泉 / hot spring in the title. The Beitou branch
    # is hot-spring themed, so the book exists; the real time sink is
    # applying for a library card if nobody on the team has one.
    "北投圖書館任務": ChallengeProfile(mean_minutes=20, sd_minutes=6, success=0.9),
    # Find one specific 3D rabbit somewhere in a multi-storey building in 10
    # minutes. Doable if they sweep floor by floor, easy to run out of time.
    "天台廣場任務": ChallengeProfile(mean_minutes=14, sd_minutes=2, success=0.8),
    # One person's dead hang, called between 30 and 60 seconds, by the team's
    # strongest member: ~94% at 30s, ~52% at 48s, ~22% at 60s.
    "蘆洲捷運公園任務": ChallengeProfile(
        mean_minutes=8, sd_minutes=2,
        call_range=(30, 60),
        success_fn=_best_of_team_hang(3),
    ),
    # Everyone takes a turn down the roller slide. Only fails if the queue
    # is absurd or the slide's closed.
    "新北大都會公園任務": ChallengeProfile(mean_minutes=12, sd_minutes=4, success=0.95),
    # Set a display laptop's browser homepage and prove it by relaunching.
    # Quick for anyone who knows their way around settings; the failure
    # modes are a locked-down demo unit or a staff member stepping in.
    "三創任務": ChallengeProfile(mean_minutes=12, sd_minutes=4, success=0.95),
    # 10 short-answer indigenous-culture trivia questions; call how many
    # you'll get right. Each question treated as an independent 50% shot
    # (organiser's estimate), so p(call n) = P(Binomial(10, 0.5) >= n).
    "石牌站任務": ChallengeProfile(
        mean_minutes=10, sd_minutes=3,
        call_range=(1, 10),
        success_fn=lambda n: _binomial_at_least(10, 0.5, n),
    ),
}

DEFAULT_PROFILE = ChallengeProfile(mean_minutes=18, sd_minutes=5, success=0.5)


def profile_for(name: str) -> ChallengeProfile:
    return PROFILES.get(name, DEFAULT_PROFILE)
