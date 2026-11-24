from __future__ import annotations

import csv
import io
from dataclasses import replace
from datetime import date, datetime
from typing import Optional

from .config import Rules
from .engine import compute_user
from .missed_day import freeze_offer, timeline
from .reminders import plan_reminders
from .models import UserResult, parse_dt
from .store import Store


class Service:
    def __init__(self, store: Store, rules: Rules, allow_received_at: bool = True):
        self.store, self.rules, self.allow_received_at = store, rules, allow_received_at

    def default_as_of(self) -> datetime:
        """'Now'. Logical clock: the exercise's 15 Nov 10:00 IST, moved forward by events POSTed at runtime,
        so POSTing events with a later received_at behaves like time passing (documented in README)."""
        mx = self.store.clock_floor()
        return max(self.rules.now, mx) if mx else self.rules.now

    def result(self, user_id: str, as_of: Optional[datetime] = None, from_day: Optional[date] = None) -> Optional[UserResult]:
        user = self.store.user(user_id)
        if user is None:
            return None
        as_of = as_of or self.default_as_of()
        res = compute_user(user, self.store.user_events(user_id, as_of), self.store.videos(), self.store.incidents(),
                           as_of, self.rules, from_day)
        res.rules_used = {"max_offline_delay_hours": self.rules.max_offline_delay_hours,
                          "min_day_seconds": self.rules.min_day_seconds, "complete_ratio": self.rules.complete_ratio}
        return res

    # ------------------------------------------------------------------ json shapes
    def streak_json(self, res: UserResult) -> dict:
        return {"user_id": res.user.user_id, "as_of": res.as_of.isoformat(), "user_local_today": res.today.isoformat(),
                "user_tz": res.tz, "current_streak": res.streak, "status": res.status, "reason": res.reason,
                "streak_if_pending_day_is_missed": res.streak_if_pending_missed,
                "pending_settles_at_utc": res.pending_final_at.isoformat() if res.pending_final_at else None,
                "freeze_balance": res.freeze_tokens, "refund_candidates": res.refund_candidates,
                "rules": res.rules_used}

    @staticmethod
    def days_json(res: UserResult) -> list[dict]:
        return [{"date": r.day.isoformat(), "code": r.code, "counts_toward_streak": r.counts, "streak_after": r.streak_after,
                 "final": r.final, "summary": r.summary, "agent_action": r.action, "notes": r.notes, "evidence": r.evidence}
                for r in res.rows]

    def missed_day_json(self, res: UserResult) -> dict:
        u = res.user
        pend = [r for r in res.rows if r.code.startswith("PENDING")]
        unsynced = False
        archetype = "forgot_premium" if (u.plan == "premium" and res.freeze_tokens > 0) else "forgot_free"
        used = sum(1 for r in res.rows if r.code == "FREEZE_USED") + len(res.refund_candidates)
        return {"user_id": u.user_id, "plan": u.plan, "freeze_balance": res.freeze_tokens,
                "freeze_offer": freeze_offer(u.plan, used, self.rules,
                                             is_new_user=(res.as_of - u.signup_at).days <= self.rules.new_user_window_days),
                "pending_days": [r.day.isoformat() for r in pend],
                "playbook_if_forgot": timeline(archetype, max(res.streak, 1)),
                "playbook_if_unsynced": timeline("unsynced", max(res.streak, 1))}

    def csv_snapshot(self, as_of: Optional[datetime] = None) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["user_id", "current_streak", "status", "reason"])
        for uid in self.store.user_ids():
            r = self.result(uid, as_of)
            w.writerow([uid, r.streak, r.status, r.reason])
        return buf.getvalue()

    def reminders_json(self, user_id: str, as_of: Optional[datetime] = None) -> Optional[dict]:
        res = self.result(user_id, as_of)
        if res is None:
            return None
        evs = self.store.user_events(user_id, res.as_of)
        grace = self.rules.live_grace_minutes * 60
        opens = sorted([e for e in evs if e.type == "app_open" and (e.rx - e.client_utc).total_seconds() <= grace],
                       key=lambda e: e.rx)
        unsynced = bool(opens and (opens[-1].queue_depth or 0) > 0)
        return plan_reminders(res, self.rules, unsynced_on_device=unsynced)
