"""All streak rules live here, in one place, so a rule change is a one-line diff.

RECORDING STEP 2: change MAX_OFFLINE_DELAY_HOURS from 7 * 24 to 36.
(Every threshold can also be overridden per run with env vars or CLI flags, see cli.py.)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone

# ---- the one number the recording asks you to change ------------------------------
MAX_OFFLINE_DELAY_HOURS = 7 * 24      # <<< change to 36 for the recording
# -----------------------------------------------------------------------------------

IST = timezone(timedelta(hours=5, minutes=30))
SNAPSHOT_NOW = datetime(2026, 11, 15, 10, 0, tzinfo=IST)   # "now" of the exercise


@dataclass(frozen=True)
class Rules:
    # What counts as a learning day (Neha vs Farhan): one lesson watched to >=80%
    # OR >=120 s of *real* watching. Lessons shorter than 2 min can't reach 120 s alone.
    complete_ratio: float = 0.80
    min_day_seconds: int = 120
    min_watch_ratio: float = 0.25        # a view below 25% of the lesson is a swipe, earns 0 s

    # Late / offline sync
    max_offline_delay_hours: float = MAX_OFFLINE_DELAY_HOURS
    live_grace_minutes: float = 15       # received - client <= this: a normal, live event
    future_tolerance_minutes: float = 5  # client clock ahead of server by more: ignore client_ts
    batch_gap_minutes: float = 15        # late events closer than this form one sync batch
    unverified_cap: int = 3              # uncorroborated back-dated lessons per rolling window
    unverified_window_days: int = 30

    # Missed-day lifecycle
    pending_hours: float = 48            # day is PENDING (not "missed") for 48 h after midnight
    auto_freeze_after_hours: float = 24  # unconfirmed day + freeze in balance: auto-use at +24 h

    # Travel
    travel_max_gap_hours: float = 48     # eastbound date-skip bridge only if lessons <=48 h apart

    # Baseline + clock
    baseline_end: date = date(2026, 10, 31)   # users.csv streak is "going into 1 Nov"
    now: datetime = SNAPSHOT_NOW

    # Monetisation knobs (do not change streak maths, only what the offer endpoint says)
    freeze_price_inr: int = 49
    free_freeze_allowance: int = 2       # first N freezes cost 0 for NEW free users only. Try 1, 2, 3.
    new_user_window_days: int = 30       # 'new' = signed up within this many days of as_of

    # Reminders (Duolingo-style, sent before the user's local day ends)
    reminder_default_hour: float = 19.0  # used when we have no history of when the user learns
    reminder_usual_min_hour: float = 16.0
    reminder_usual_max_hour: float = 20.0
    reminder_evening_hour: float = 21.0  # 'streak ends at midnight'
    reminder_final_hour: float = 22.5    # last call, 90 min before midnight
    reminder_no_push_before_hour: float = 8.0


def rules_from_env(base: Rules | None = None) -> Rules:
    r = base or Rules()
    v = os.environ.get("JUMPP_MAX_OFFLINE_HOURS")
    if v:
        r = replace(r, max_offline_delay_hours=float(v))
    v = os.environ.get("JUMPP_FREE_FREEZE_ALLOWANCE")
    if v:
        r = replace(r, free_freeze_allowance=int(v))
    return r
