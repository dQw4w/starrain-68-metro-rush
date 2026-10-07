"""Every knob the simulation turns, in one place.

This is the file you edit when tuning. The point of the whole `sim/` package
is to answer "what starting chips and challenge rewards make the two teams
finish close together?", so the parameters that answer that question live
here rather than being scattered through the engine.

Nothing here is read by the deployed app — `sim/` is local-only tooling.
"""
from dataclasses import dataclass, field


# Stations where the two lines share a platform, so changing lines costs only
# the wait for the next train — no walking between platforms.
#
# VERIFY THESE AGAINST REALITY before trusting a tuning run: they shave 2
# minutes off every transfer that uses them, which moves results. Listed as
# the station name exactly as it appears in backend/seed_stations.py.
CROSS_PLATFORM_TRANSFERS: set[str] = {
    "古亭",        # 中和新蘆線 ↔ 松山新店線
    "東門",        # 中和新蘆線 ↔ 淡水信義線
    # "民權西路",    # 淡水信義線 ↔ 中和新蘆線
    "大橋頭",      # 中和新蘆線 ↔ 蘆洲支線
    "七張",        # 松山新店線 ↔ 小碧潭支線
    "北投",        # 淡水信義線 ↔ 新北投支線
    "西門",        # 
    "中正紀念堂",  # 
}


@dataclass
class SimConfig:
    # --- what we're tuning -------------------------------------------------
    #: Starting chips per team, keyed by the team label used in results.
    starting_chips: dict[str, int] = field(
        default_factory=lambda: {"科技大樓隊": 25, "公館隊": 25}
    )
    #: Where each team begins, as a station name from seed_stations.py.
    start_stations: dict[str, str] = field(
        default_factory=lambda: {"科技大樓隊": "科技大樓", "公館隊": "公館"}
    )
    #: Override a challenge's reward without editing seed_challenges.py, e.g.
    #: {"西門町任務": {"chips": 60}}. Merged over the seeded reward_config.
    challenge_reward_overrides: dict[str, dict] = field(default_factory=dict)

    # --- game rules (mirror the real backend) ------------------------------
    game_minutes: int = 6 * 60
    max_deposit_per_visit: int = 5
    fail_bonus_step_pct: float = 10.0
    #: True  → every challenge is on the map from minute 0, which is what the
    #:          superadmin's 上架所有任務 button does. Much less noisy to tune
    #:          against, because results don't depend on the reveal order.
    #: False → mirror the live pool: start with `challenge_pool_initial`
    #:          fixed-reward challenges revealed, and reveal
    #:          `challenge_pool_refill` more each time one is completed.
    all_challenges_active: bool = False
    challenge_pool_initial: int = 3
    challenge_pool_refill: int = 2
    #: Pin exactly which challenges start revealed, by name, instead of
    #: letting the opening pool be drawn at random from the fixed-reward
    #: ones. Use this to make sure each team has something within reach at
    #: minute 0 — a random opening draw can put all three on the far side of
    #: the city and leave both teams with nothing to do but claim stations.
    #: None = keep the live behaviour (random fixed-reward draw).
    initial_active_challenges: list[str] | None = None

    # --- transit model -----------------------------------------------------
    minutes_per_segment: int = 2
    wait_minutes: int = 2
    transfer_walk_minutes: int = 2
    transfer_wait_minutes: int = 2
    #: Brisk urban walking. 80 m/min ≈ 4.8 km/h.
    walk_speed_m_per_min: float = 80.0
    #: Straight-line distance underestimates street walking; scale it up.
    walk_detour_factor: float = 1.3
    #: Challenges further than this on foot aren't offered as an option from
    #: a station — keeps the option list readable and the agent sane.
    max_walk_minutes: int = 25
    #: Tapping through a claim/top-up on the phone.
    claim_minutes: int = 1
    #: How long a "wait here" action burns.
    idle_wait_minutes: int = 5

    # --- agent / LLM -------------------------------------------------------
    #: How many nearest challenges to offer at any one decision.
    max_challenge_options: int = 4
    #: Cap on LLM calls per team per game; past this the heuristic takes over
    #: so a slow local model can't hang a sweep forever. 0 = no cap.
    max_llm_calls_per_team: int = 0

    seed: int | None = None
