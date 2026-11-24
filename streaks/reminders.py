"""'Your streak ends tonight' reminders, Duolingo-style: sent in the user's own evening, before THEIR midnight.

Plan for the user's local today (a pure function of the streak result, so notifications and the
streak engine can never disagree):
  1. at the user's usual lesson time (median of recent live lessons, clamped 16:00-20:00; default 19:00)  - gentle
  2. 21:00  - "ends at midnight"                                                                      - urgent
  3. 22:30  - last call (only for streaks worth saving)                                              - final
Never sent when: already learned today; a lesson is still waiting to sync on the phone (queue_depth>0);
before 08:00 local; or after the time has passed. Max 3 a day. We do not push a Freeze purchase here:
that offer belongs to the missed-day flow (missed_day.py) where we KNOW the day was missed.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from .config import Rules
from .models import UTC, UserResult


def usual_hour(res: UserResult, rules: Rules) -> float:
    hrs = []
    for r in res.rows[-14:]:
        for l in r.evidence.get("lessons", []):
            if l["trust"] == "LIVE":
                hh, mm = l["claimed_local"][11:16].split(":")
                hrs.append(int(hh) + int(mm) / 60)
    h = median(hrs) if hrs else rules.reminder_default_hour
    return min(max(h, rules.reminder_usual_min_hour), rules.reminder_usual_max_hour)


def _at(day, hour: float, tz: str) -> datetime:
    h, m = int(hour), int(round((hour - int(hour)) * 60))
    return datetime.combine(day, time(h, m), tzinfo=ZoneInfo(tz))


def plan_reminders(res: UserResult, rules: Rules, unsynced_on_device: bool = False) -> dict:
    base = {"user_id": res.user.user_id, "as_of": res.as_of.isoformat(), "local_today": res.today.isoformat(),
            "tz": res.tz, "streak": res.streak, "reminders": []}
    if res.status == "SAFE_TODAY":
        return {**base, "suppressed": "already learned today"}
    if unsynced_on_device:
        return {**base, "suppressed": "device reports unsynced events: the lesson may already be done, do not nag"}
    s = res.streak
    tz = res.tz
    midnight = _at(res.today + timedelta(days=1), 0, tz)
    plan = []
    usual = usual_hour(res, rules)
    if s > 0:
        plan.append(("usual_time", usual, "Time for today's lesson",
                     f"Keep your {s}-day streak going: one short lesson does it."))
        plan.append(("evening", max(rules.reminder_evening_hour, usual + 0.5), f"Your {s}-day streak ends at midnight",
                     "A 2-minute lesson saves it. Do it now."))
        if s >= 3:
            plan.append(("final", rules.reminder_final_hour, f"Last chance: {s} days on the line",
                         "Only a few minutes left today. One lesson keeps your streak alive."))
    else:
        plan.append(("usual_time", usual, "Start a new streak today", "One short lesson starts day 1."))
    out = []
    for kind, hour, title, body in plan:
        if hour < rules.reminder_no_push_before_hour:
            continue
        send = _at(res.today, hour, tz)
        if send <= res.as_of or send >= midnight:
            continue
        out.append({"kind": kind, "send_at_local": send.strftime("%Y-%m-%d %H:%M"), "send_at_utc": send.astimezone(UTC).isoformat(),
                    "hours_left_in_day": round((midnight - send).total_seconds() / 3600, 1), "title": title, "body": body})
    return {**base, "reminders": out[:3], "suppressed": None if out else "no reminder slots left today"}
