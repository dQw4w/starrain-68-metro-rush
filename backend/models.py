from datetime import date, datetime, time
from typing import Any, Literal, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """Super admin only — team admins use a private link (see /auth/login-link), not a PIN."""
    pin: str


class LoginResponse(BaseModel):
    token: str
    admin_id: int
    team_id: Optional[int]
    display_name: str
    is_super: bool


class WsTicketResponse(BaseModel):
    ticket: str


# ---------------------------------------------------------------------------
# Game config
# ---------------------------------------------------------------------------

class GameConfig(BaseModel):
    team_count: int
    game_date: date
    start_time: time
    end_time: time
    lunch_start: time
    lunch_end: time
    starting_chips: int
    max_deposit_per_visit: int
    fail_bonus_step_pct: float
    challenge_pool_initial: int
    challenge_pool_refill: int
    challenge_pool_max: int
    override_status: Literal["auto", "paused", "force_ended"]
    locked: bool


class GameConfigUpdate(BaseModel):
    team_count: Optional[int] = None
    game_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    lunch_start: Optional[time] = None
    lunch_end: Optional[time] = None
    starting_chips: Optional[int] = None
    max_deposit_per_visit: Optional[int] = None
    fail_bonus_step_pct: Optional[float] = None
    challenge_pool_initial: Optional[int] = None
    challenge_pool_refill: Optional[int] = None
    challenge_pool_max: Optional[int] = None
    override_status: Optional[Literal["auto", "paused", "force_ended"]] = None
    locked: Optional[bool] = None


class GamePhase(BaseModel):
    phase: Literal["not_started", "active", "lunch_break", "ended", "paused"]
    server_time: datetime
    game_date: date
    start_at: datetime
    end_at: datetime
    lunch_start_at: datetime
    lunch_end_at: datetime


# ---------------------------------------------------------------------------
# Lines / Stations
# ---------------------------------------------------------------------------

class Line(BaseModel):
    id: int
    code: str
    name_zh: str
    name_en: str
    color_hex: str
    sort_order: int


class LineCreate(BaseModel):
    code: str
    name_zh: str
    name_en: str
    color_hex: str
    sort_order: int = 0


class Station(BaseModel):
    id: int
    name_zh: str
    name_en: str
    lat: float
    lng: float
    line_ids: list[int] = []


class StationCreate(BaseModel):
    name_zh: str
    name_en: str
    lat: float
    lng: float
    lines: list[dict[str, int]] = []  # [{line_id, sequence}]


class StationUpdate(BaseModel):
    name_zh: Optional[str] = None
    name_en: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class StationClaim(BaseModel):
    station_id: int
    owner_team_id: Optional[int]
    value: int
    cap: int
    updated_at: datetime


class MapData(BaseModel):
    lines: list[Line]
    stations: list[Station]
    claims: list[StationClaim]
    # line_id (as str) -> ordered [lat, lng] points (real stations + invisible
    # line_waypoints interleaved by sequence), ready to draw as a polyline.
    line_paths: dict[str, list[list[float]]]


class LineStationOrderEntry(BaseModel):
    station_id: int
    name_zh: str
    lat: float
    lng: float
    sequence: int


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

class TeamPublic(BaseModel):
    id: int
    name: str
    color_hex: str
    meeting_station_id: Optional[int]
    chips_balance: int
    active: bool
    stations_owned: int = 0
    rank: int = 0


class TeamAdminView(TeamPublic):
    share_token: str
    admin_share_token: str


class TeamCreate(BaseModel):
    name: str
    color_hex: str = "#3B82F6"
    meeting_station_id: Optional[int] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    color_hex: Optional[str] = None
    meeting_station_id: Optional[int] = None
    active: Optional[bool] = None


class TeamSelf(BaseModel):
    id: int
    name: str
    color_hex: str
    meeting_station_id: Optional[int]
    chips_balance: int
    share_token: str


# ---------------------------------------------------------------------------
# Approval requests / claims
# ---------------------------------------------------------------------------

class ClaimRequestCreate(BaseModel):
    station_id: int
    kind: Literal["claim", "topup"]
    amount: int
    requested_by: Optional[str] = None


class PublicGameConfig(BaseModel):
    starting_chips: int
    max_deposit_per_visit: int
    fail_bonus_step_pct: float


class ApprovalRequestOut(BaseModel):
    id: int
    kind: Literal["claim", "topup", "challenge_start", "challenge_result"]
    team_id: int
    station_id: Optional[int]
    challenge_id: Optional[int]
    challenge_attempt_id: Optional[int]
    requested_by: Optional[str]
    requested_value: dict[str, Any]
    status: Literal["pending", "approved", "denied", "stale"]
    resolved_by: Optional[int]
    resolved_at: Optional[datetime]
    created_at: datetime


class ResolveChallengeResultBody(BaseModel):
    success: bool
    achieved_value: Optional[int] = None


class DenyRequestBody(BaseModel):
    reason: Optional[str] = None


class AdjustChipsBody(BaseModel):
    delta: int
    reason: str


class SetBalanceBody(BaseModel):
    balance: int


class ReleaseStationsBody(BaseModel):
    station_ids: Optional[list[int]] = None  # None/omitted = release every station this team owns


# ---------------------------------------------------------------------------
# Challenges
# ---------------------------------------------------------------------------

RewardConfig = dict[str, Any]
# fixed:      {"chips": 30}
# variable:   {"chips_per_unit": 8, "unit_label": "正確答案數"}
# steal:      {"steal_pct": 45}
# multiplier: {"multiplier_pct": 45}


class Challenge(BaseModel):
    id: int
    name: str
    description: str
    type: Literal["fixed", "variable", "steal", "multiplier"]
    reward_config: RewardConfig
    location_name: Optional[str]
    lat: Optional[float]
    lng: Optional[float]
    image_url: Optional[str]
    pool_state: Literal["queued", "active", "retired"]


class ChallengeTeaser(BaseModel):
    """Public listing shape: location + reward are known upfront, but the task
    description itself stays hidden until a team's admin approves the start
    (rule: description pops up on the team's screens only after approval)."""
    id: int
    name: str
    type: Literal["fixed", "variable", "steal", "multiplier"]
    reward_config: RewardConfig
    location_name: Optional[str]
    lat: Optional[float]
    lng: Optional[float]
    image_url: Optional[str]
    pool_state: Literal["queued", "active", "retired"]


class ChallengeCreate(BaseModel):
    name: str
    description: str
    type: Literal["fixed", "variable", "steal", "multiplier"]
    reward_config: RewardConfig
    location_name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    image_url: Optional[str] = None
    pool_state: Literal["queued", "active", "retired"] = "queued"


class ChallengeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[Literal["fixed", "variable", "steal", "multiplier"]] = None
    reward_config: Optional[RewardConfig] = None
    location_name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    image_url: Optional[str] = None
    pool_state: Optional[Literal["queued", "active", "retired"]] = None


class ChallengeAttempt(BaseModel):
    id: int
    challenge_id: int
    team_id: int
    status: Literal["pending_start_approval", "in_progress", "pending_result", "success", "failed"]
    called_shot_value: Optional[int]
    achieved_value: Optional[int]
    target_team_id: Optional[int]
    fail_bonus_pct_locked: float
    reward_amount: Optional[int]
    started_at: Optional[datetime]
    resolved_at: Optional[datetime]


class ChallengeStartRequest(BaseModel):
    called_shot_value: Optional[int] = None
    target_team_id: Optional[int] = None
    requested_by: Optional[str] = None


class ChallengeSubmitResultRequest(BaseModel):
    achieved_value: Optional[int] = None


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------

class ActionLogEntry(BaseModel):
    id: int
    team_id: int
    team_name: str
    actor: str
    action_type: str
    station_id: Optional[int]
    challenge_id: Optional[int]
    chip_delta: Optional[int]
    resulting_balance: Optional[int]
    message: str
    created_at: datetime


# ---------------------------------------------------------------------------
# GPS
# ---------------------------------------------------------------------------

class GpsPing(BaseModel):
    device_id: str
    lat: float
    lng: float


class DevicePosition(BaseModel):
    team_id: int
    device_id: str
    lat: float
    lng: float
    updated_at: datetime


# ---------------------------------------------------------------------------
# Team state (aggregate, for the team page)
# ---------------------------------------------------------------------------

class TeamState(BaseModel):
    team: TeamSelf
    phase: GamePhase
    ranking: list[TeamPublic]
    pending_requests: list[ApprovalRequestOut]
