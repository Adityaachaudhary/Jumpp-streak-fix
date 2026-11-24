from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

UTC = timezone.utc


def parse_dt(s: str, default_tz: Optional[str] = None) -> datetime:
    """ISO-8601 -> aware UTC datetime. Accepts 'Z' and offsets."""
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        if default_tz:
            from zoneinfo import ZoneInfo
            d = d.replace(tzinfo=ZoneInfo(default_tz))
        else:
            d = d.replace(tzinfo=UTC)
    return d.astimezone(UTC)


def parse_meta(s: Optional[str]) -> dict:
    out = {}
    for part in (s or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


@dataclass(frozen=True)
class Ev:
    event_id: str
    user_id: str
    type: str
    video_id: Optional[str]
    watched_s: Optional[int]
    client_utc: datetime
    device_tz: str
    rx: datetime              # server received_at (UTC): the only clock we trust by default
    app_version: str
    meta: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def queue_depth(self) -> Optional[int]:
        v = self.meta.get("queue_depth")
        return int(v) if v is not None and v.isdigit() else None


@dataclass(frozen=True)
class User:
    user_id: str
    name: str
    signup_at: datetime
    home_tz: str
    plan: str
    freeze_balance: int
    streak_baseline: int       # streak going into 1 Nov


@dataclass(frozen=True)
class Video:
    video_id: str
    title: str
    duration_s: int
    published_at: datetime


@dataclass(frozen=True)
class Incident:
    incident_id: str
    start: datetime
    end: datetime
    description: str
    affected_uids: frozenset


@dataclass
class Lesson:
    video_id: str
    watched_s: int
    duration_s: Optional[int]
    start_utc: datetime        # claimed (client) start
    end_utc: datetime
    end_rx: datetime           # when the server learned it finished
    tz: str
    app_version: str
    published_utc: Optional[datetime]
    end_event_id: str
    delay_s: float
    trust: str = "LIVE"        # LIVE | LATE_VERIFIED | LATE_UNVERIFIED | FUTURE_TS | REJECTED_*
    detail: str = ""
    claimed_day: Optional[date] = None
    credit_day: Optional[date] = None

    @property
    def rejected(self) -> bool:
        return self.trust.startswith("REJECTED_")

    @property
    def ratio(self) -> float:
        return self.watched_s / self.duration_s if self.duration_s else 1.0


@dataclass
class DayRow:
    day: date
    code: str
    counts: int                # +1 if this day adds to the streak, else 0
    streak_after: int
    summary: str
    action: str = ""
    notes: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    final: bool = True


@dataclass
class UserResult:
    user: User
    as_of: datetime
    today: date
    tz: str
    streak: int
    status: str
    reason: str
    rows: list
    streak_if_pending_missed: Optional[int]
    freeze_tokens: int
    refund_candidates: list
    pending_final_at: Optional[datetime]
    broken_on: Optional[date]
    rules_used: dict
