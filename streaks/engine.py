"""The streak engine: a pure function of (user, events received <= as_of, reference data, rules).

Nothing here reads a clock or touches storage, so the same event *set* always gives the same answer
no matter what order or in which batches the events arrived (tests/test_order_independence.py).

Pipeline
  1. dedupe()           collapse re-sent events (same id, or regenerated ids with identical content)
  2. build_lessons()    pair video_start/video_end into lessons
  3. classify_trust()   live / late-verified / late-unverified / rejected (+ reason)
  4. assign_local_day() put each lesson on a calendar day               <-- RECORDING STEP 1
  5. walk_days()        day-by-day state machine -> reason code per day, streak, status
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from .config import Rules
from .models import DayRow, Ev, Incident, Lesson, User, UserResult, Video, UTC

# ----------------------------------------------------------------------------- 1. dedupe


def _sem_key(e: Ev):
    if e.type == "freeze_purchase":
        return (e.type, e.meta.get("order") or e.event_id)
    return (e.type, e.video_id, e.client_utc, e.meta.get("for_date") if e.type == "freeze_applied" else None)


def dedupe(events: list[Ev]) -> tuple[list[Ev], dict]:
    """Keep one copy per semantic key: earliest received, then smallest event_id (arrival-order free).
    Catches both re-sent batches (same event_id) and the 3.1.x bug that regenerated ids on retry."""
    kept: dict = {}
    dropped = defaultdict(int)       # local-ish bucket: client date -> n dropped
    for e in sorted(events, key=lambda e: (e.rx, e.event_id)):
        k = _sem_key(e)
        if k in kept:
            dropped[e.client_utc.astimezone(ZoneInfo(e.device_tz)).date()] += 1
        else:
            kept[k] = e
    return sorted(kept.values(), key=lambda e: (e.client_utc, e.event_id)), dict(dropped)


# --------------------------------------------------------------------------- 2. lessons


def build_lessons(events: list[Ev], videos: dict[str, Video]) -> tuple[list[Lesson], list[Ev]]:
    starts = [e for e in events if e.type == "video_start"]
    ends = [e for e in events if e.type == "video_end"]
    used: set = set()
    lessons: list[Lesson] = []
    for end in sorted(ends, key=lambda e: (e.client_utc, e.event_id)):
        cand = [s for s in starts if s.video_id == end.video_id and s.event_id not in used
                and timedelta(0) <= end.client_utc - s.client_utc <= timedelta(minutes=30)]
        start = max(cand, key=lambda s: (s.client_utc, s.event_id)) if cand else None
        if start:
            used.add(start.event_id)
        v = videos.get(end.video_id)
        start_utc = start.client_utc if start else end.client_utc - timedelta(seconds=end.watched_s or 0)
        lessons.append(Lesson(video_id=end.video_id, watched_s=end.watched_s or 0, duration_s=v.duration_s if v else None,
                              start_utc=start_utc, end_utc=end.client_utc, end_rx=end.rx, tz=end.device_tz,
                              app_version=end.app_version, published_utc=v.published_at if v else None,
                              end_event_id=end.event_id, delay_s=(end.rx - end.client_utc).total_seconds()))
    orphans = [s for s in starts if s.event_id not in used]
    return lessons, orphans


# ------------------------------------------------------------------------ 3. trust


def _clusters(late_events: list[Ev], gap: timedelta) -> dict[str, tuple[int, datetime, datetime]]:
    """Late events received close together = one offline sync batch. Returns event_id -> (size, first_rx, last_rx)."""
    out, cur = {}, []
    for e in sorted(late_events, key=lambda e: (e.rx, e.event_id)):
        if cur and e.rx - cur[-1].rx > gap:
            _flush(cur, out)
            cur = []
        cur.append(e)
    if cur:
        _flush(cur, out)
    return out


def _flush(cur, out):
    info = (len(cur), cur[0].rx, cur[-1].rx)
    for e in cur:
        out[e.event_id] = info


def classify_trust(lessons: list[Lesson], events: list[Ev], rules: Rules) -> None:
    grace = timedelta(minutes=rules.live_grace_minutes)
    fut = timedelta(minutes=rules.future_tolerance_minutes)
    max_delay = timedelta(hours=rules.max_offline_delay_hours).total_seconds()

    def late(e: Ev) -> bool:
        return e.rx - e.client_utc > grace

    batch_events = [e for e in events if e.type in ("app_open", "video_start", "video_end") and late(e)]
    clusters = _clusters(batch_events, timedelta(minutes=rules.batch_gap_minutes))
    live_opens = sorted([e for e in events if e.type == "app_open" and not late(e)], key=lambda e: (e.rx, e.event_id))

    unverified: list[Lesson] = []
    for l in lessons:
        if l.delay_s < -fut.total_seconds():
            l.trust, l.detail = "FUTURE_TS", "client clock ahead of server; credited at server receipt time"
            continue
        if l.delay_s <= grace.total_seconds():
            l.trust = "LIVE"
            continue
        # ---- late: someone claims this lesson happened earlier than the server heard about it
        hours = l.delay_s / 3600
        if l.delay_s > max_delay:
            l.trust, l.detail = "REJECTED_TOO_OLD", f"claimed {hours:.1f} h earlier; limit is {rules.max_offline_delay_hours:g} h"
            continue
        if l.published_utc and l.start_utc < l.published_utc:
            l.trust = "REJECTED_UNPUBLISHED"
            l.detail = (f"lesson {l.video_id} was published {l.published_utc.isoformat()} but the claimed watch time is "
                        f"{l.start_utc.isoformat()}: it did not exist yet")
            continue
        size, first_rx, last_rx = clusters.get(l.end_event_id, (1, l.end_rx, l.end_rx))
        recon = [o for o in live_opens if l.start_utc <= o.rx <= last_rx]
        qd = recon[-1].queue_depth if recon else None
        if qd is None:
            l.trust, l.detail = "LATE_UNVERIFIED", f"{hours:.1f} h late; device sent no queue_depth (old app) - accepted on plausibility"
            unverified.append(l)
        elif qd < size:
            l.trust = "REJECTED_QUEUE_MISMATCH"
            l.detail = f"device said {qd} events were unsynced when it reconnected, but a batch of {size} arrived"
        else:
            l.trust, l.detail = "LATE_VERIFIED", f"{hours:.1f} h late; device reported queue_depth={qd} for a batch of {size}"
    # cap on uncorroborated back-dating (anti-farming), applied in claimed-time order
    window = timedelta(days=rules.unverified_window_days)
    accepted: list[Lesson] = []
    for l in sorted(unverified, key=lambda l: (l.start_utc, l.end_event_id)):
        recent = [a for a in accepted if timedelta(0) <= l.start_utc - a.start_utc < window]
        if len(recent) >= rules.unverified_cap:
            l.trust = "REJECTED_CAP"
            l.detail = f"{len(recent)} uncorroborated back-dated lessons already accepted in {rules.unverified_window_days} days"
        else:
            accepted.append(l)


# --------------------------------------------------------------------- 4. day assignment


def assign_local_day(l: Lesson) -> date:
    """RECORDING STEP 1 - the ONE place a lesson is put on a calendar day.

    Rules: (a) the day is the user's *local* date at the moment the lesson STARTED, in the timezone the
    device was in (so travel can't shift it and a lesson straddling midnight belongs to the day it began);
    (b) a lesson we trust uses the client's clock; (c) one we reject, or whose clock is in the future,
    is credited at SERVER receipt time - the lesson still happened, just not earlier than we heard of it.
    """
    instant = l.start_utc if l.trust in ("LIVE", "LATE_VERIFIED", "LATE_UNVERIFIED") else l.end_rx
    return instant.astimezone(ZoneInfo(l.tz)).date()


def claimed_day(l: Lesson) -> date:
    return l.start_utc.astimezone(ZoneInfo(l.tz)).date()


# ------------------------------------------------------------------- 5. the day walk


def _qualifies(lessons: list[Lesson], rules: Rules) -> tuple[bool, bool, int]:
    """-> (counts, swipe_only, credited_seconds). Same video repeated in a day counts once (max view)."""
    best: dict[str, Lesson] = {}
    for l in lessons:
        if l.video_id not in best or l.watched_s > best[l.video_id].watched_s:
            best[l.video_id] = l
    credited, completed, any_real = 0, False, False
    for l in best.values():
        if l.ratio >= rules.min_watch_ratio:
            any_real = True
            credited += min(l.watched_s, l.duration_s or l.watched_s)
        if l.duration_s and l.ratio >= rules.complete_ratio:
            completed = True
    return (completed or credited >= rules.min_day_seconds), (not any_real), credited


def _lesson_ev(l: Lesson) -> dict:
    return {"video": l.video_id, "watched_s": l.watched_s, "duration_s": l.duration_s,
            "ratio": round(l.ratio, 2), "trust": l.trust, "delay_h": round(l.delay_s / 3600, 1),
            "claimed_local": l.start_utc.astimezone(ZoneInfo(l.tz)).strftime("%Y-%m-%d %H:%M"),
            "received_utc": l.end_rx.strftime("%Y-%m-%d %H:%M:%S"), "detail": l.detail}


SUMMARY = {
    "LEARNED": "Learned (live).",
    "LEARNED_LATE_VERIFIED": "Learned offline; synced later and the device's own queue count matches.",
    "LEARNED_LATE_UNVERIFIED": "Learned offline per a late sync we could not corroborate (old app); accepted on plausibility.",
    "OUTAGE_PROTECTED": "No lesson recorded, but this user was hit by the 9 Nov ingestion outage: day protected (bridges, adds 0).",
    "TRAVEL_BRIDGED": "Calendar date skipped by an eastbound timezone change: day bridged (adds 0).",
    "FREEZE_USED": "Missed day covered by a Streak Freeze (adds 0).",
    "PENDING_SYNC": "No lesson yet. Might still be on the phone: waiting, nothing is lost yet.",
    "PENDING_FREEZE_OFFER": "Device confirmed nothing is waiting to sync: day is missed unless a Freeze is used before the window closes.",
    "TODAY_OPEN": "Today is still in progress, no lesson yet.",
    "MISSED_NO_ACTIVITY": "No lesson watched.",
    "MISSED_SWIPE_ONLY": "Videos were opened but each was closed within seconds: no real watching.",
    "MISSED_BELOW_THRESHOLD": "Some watching, but below one completed lesson or 2 minutes.",
    "MISSED_START_ONLY": "A lesson was started but never finished and nothing is queued on the device.",
    "MISSED_BACKDATE_UNPUBLISHED": "Back-dated claim rejected: the lesson did not exist yet at the claimed time.",
    "MISSED_BACKDATE_QUEUE_MISMATCH": "Back-dated claim rejected: device queue count contradicts the batch.",
    "MISSED_BACKDATE_TOO_OLD": "Back-dated claim rejected: arrived later than the maximum offline delay.",
    "MISSED_BACKDATE_CAP": "Back-dated claim rejected: too many uncorroborated back-dated lessons recently.",
    "PRE_SIGNUP": "Before the user signed up.",
}

ACTION = {
    "LEARNED": "-",
    "LEARNED_LATE_VERIFIED": "Nothing to do. Offline claim was corroborated by the device.",
    "LEARNED_LATE_UNVERIFIED": "Nothing to do. If this user shows 3+ of these a month, flag for T&S review.",
    "OUTAGE_PROTECTED": "Tell user it was our outage; streak kept. A protected day keeps the streak alive but does not add a day. No freeze was used.",
    "TRAVEL_BRIDGED": "Nothing to do. Explain: crossing the date line skipped a calendar date; streak kept (no day added).",
    "FREEZE_USED": "Freeze consumed. Confirm balance with user if asked.",
    "PENDING_SYNC": "Do NOT restore, refund or promise anything yet. Ask user to open the app online; check again after the window.",
    "PENDING_FREEZE_OFFER": "Freeze offer is live until the window closes. Do not promise a restore; a Freeze (or a synced lesson) saves it.",
    "TODAY_OPEN": "Nothing - today is not over.",
    "MISSED_NO_ACTIVITY": "No lesson found. No restore. Suggest a Freeze for next time. If user insists they watched offline, ask for the app version + device time and escalate.",
    "MISSED_SWIPE_ONLY": "Do NOT restore. Explain the rule kindly (1 lesson watched 80%+ or 2 min total); opening the app is not learning. Not an accusation.",
    "MISSED_BELOW_THRESHOLD": "Explain the rule; no restore.",
    "MISSED_START_ONLY": "Ask user to retry; check crash logs / app killed mid-video. No restore unless engineering finds a client bug.",
    "MISSED_BACKDATE_UNPUBLISHED": "Do NOT restore. Neutral tone, no accusation. If user disputes, escalate to T&S with the evidence line.",
    "MISSED_BACKDATE_QUEUE_MISMATCH": "Do NOT restore. Neutral tone; escalate to T&S if disputed.",
    "MISSED_BACKDATE_TOO_OLD": "Do NOT restore (older than the offline limit). Product fix: nudge users to sync within the limit.",
    "MISSED_BACKDATE_CAP": "T&S review: repeated uncorroborated back-dating.",
    "PRE_SIGNUP": "-",
}


def _local_midnight_utc(d: date, tz: str) -> datetime:
    return datetime.combine(d, time(0), tzinfo=ZoneInfo(tz)).astimezone(UTC)


def compute_user(user: User, events: list[Ev], videos: dict[str, Video], incidents: list[Incident],
                 as_of: datetime, rules: Rules, from_day: Optional[date] = None) -> UserResult:
    events = [e for e in events if e.rx <= as_of]
    uniq, dup_by_day = dedupe(events)
    lessons, orphans = build_lessons(uniq, videos)
    classify_trust(lessons, uniq, rules)
    grace = timedelta(minutes=rules.live_grace_minutes)

    # ---- timezone timeline from live events + explicit tz_change events
    pts = sorted([(e.client_utc, e.device_tz) for e in uniq
                  if (e.type == "tz_change") or (e.rx - e.client_utc <= grace)])
    tz_changes = [e for e in uniq if e.type == "tz_change"]
    initial_tz = (tz_changes[0].meta.get("from") if tz_changes else None) or user.home_tz

    def tz_at(t: datetime) -> str:
        cur = initial_tz
        for ts, tz in pts:
            if ts <= t:
                cur = tz
            else:
                break
        return cur

    tz_now = tz_at(as_of)
    today = as_of.astimezone(ZoneInfo(tz_now)).date()
    signup_day = user.signup_at.astimezone(ZoneInfo(user.home_tz)).date()
    first_day = max(rules.baseline_end + timedelta(days=1), signup_day)

    # ---- bucket lessons by day
    by_day: dict[date, list[Lesson]] = defaultdict(list)
    rejected_by_claim: dict[date, list[Lesson]] = defaultdict(list)
    for l in lessons:
        l.credit_day = assign_local_day(l)
        l.claimed_day = claimed_day(l)
        by_day[l.credit_day].append(l)
        if l.rejected:
            rejected_by_claim[l.claimed_day].append(l)
    orphan_days: dict[date, list[Ev]] = defaultdict(list)
    for o in orphans:
        orphan_days[o.client_utc.astimezone(ZoneInfo(o.device_tz)).date()].append(o)
    opens_by_day: dict[date, int] = defaultdict(int)
    for e in uniq:
        if e.type == "app_open" and e.rx - e.client_utc <= grace:
            opens_by_day[e.client_utc.astimezone(ZoneInfo(e.device_tz)).date()] += 1

    live_opens = sorted([e for e in uniq if e.type == "app_open" and e.rx - e.client_utc <= grace], key=lambda e: e.rx)
    purchases = sorted([e for e in uniq if e.type == "freeze_purchase"], key=lambda e: (e.rx, e.event_id))
    applied = [e for e in uniq if e.type == "freeze_applied"]
    inc_hits = [i for i in incidents if user.user_id in i.affected_uids]

    # tz transitions that skip calendar dates (eastbound travel)
    skips: list[tuple[date, datetime]] = []
    for e in tz_changes:
        frm = e.meta.get("from")
        if not frm:
            continue
        d_old = e.client_utc.astimezone(ZoneInfo(frm)).date()
        d_new = e.client_utc.astimezone(ZoneInfo(e.device_tz)).date()
        for k in range((d_new - d_old).days):
            skips.append((d_old + timedelta(days=k), e.client_utc))

    credited_instants = sorted(l.start_utc if l.trust in ("LIVE", "LATE_VERIFIED", "LATE_UNVERIFIED") else l.end_rx
                               for l in lessons)

    rows: list[DayRow] = []
    streak = user.streak_baseline
    tokens_base = user.freeze_balance
    consumed = 0
    pending_first_streak: Optional[int] = None     # streak value just before the first pending day
    since_pending = 0
    pending_final_at: Optional[datetime] = None
    broken_on: Optional[date] = None
    breaks: list = []                              # (day, code, streak_lost)
    tz_prev = initial_tz
    D = first_day
    last_learned_day: Optional[date] = None
    while D <= today:
        noon = datetime.combine(D, time(12), tzinfo=ZoneInfo(tz_prev)).astimezone(UTC)
        tz_d = tz_at(noon)
        tz_prev = tz_d
        ls = by_day.get(D, [])
        ok, swipe_only, credited = _qualifies(ls, rules) if ls else (False, False, 0)
        ev = {"lessons": [_lesson_ev(l) for l in sorted(ls, key=lambda l: l.start_utc)],
              "claims_rejected": [_lesson_ev(l) for l in rejected_by_claim.get(D, [])],
              "orphan_starts": len(orphan_days.get(D, [])), "app_opens": opens_by_day.get(D, 0),
              "duplicates_dropped": dup_by_day.get(D, 0), "credited_s": credited, "tz": tz_d}
        notes = []
        if dup_by_day.get(D):
            notes.append(f"{dup_by_day[D]} duplicate event(s) from a resent batch were ignored")
        if ok:
            streak += 1
            if pending_first_streak is not None:
                since_pending += 1
            live = [l for l in ls if l.trust in ("LIVE", "FUTURE_TS") or l.rejected]
            real = [l for l in ls if l.ratio >= rules.min_watch_ratio]
            if any(l.trust == "LATE_VERIFIED" for l in real) and not live:
                code = "LEARNED_LATE_VERIFIED"
            elif any(l.trust == "LATE_UNVERIFIED" for l in real) and not live:
                code = "LEARNED_LATE_UNVERIFIED"
            else:
                code = "LEARNED"
            if any(l.rejected for l in ls):
                notes.append("includes a lesson credited at server-receipt time because its back-dated claim was rejected")
            last_learned_day = D
            rows.append(DayRow(D, code, 1, streak, SUMMARY[code], ACTION[code], notes, ev))
            D += timedelta(days=1)
            continue

        if D == today:
            rows.append(DayRow(D, "TODAY_OPEN", 0, streak, SUMMARY["TODAY_OPEN"], ACTION["TODAY_OPEN"], notes, ev, final=False))
            break

        t0 = _local_midnight_utc(D + timedelta(days=1), tz_d)          # end of D
        # ---- protections that do not cost the user a freeze (outage = our fault; travel = calendar artefact)
        d_start = _local_midnight_utc(D, tz_d)
        if any(i.start < t0 and i.end > d_start for i in inc_hits):
            rows.append(DayRow(D, "OUTAGE_PROTECTED", 0, streak, SUMMARY["OUTAGE_PROTECTED"], ACTION["OUTAGE_PROTECTED"], notes, ev))
            D += timedelta(days=1)
            continue
        skip = next((s for s in skips if s[0] == D), None)
        if skip:
            before = [t for t in credited_instants if t < skip[1]]
            after = [t for t in credited_instants if t > skip[1]]
            gap_ok = bool(before) and ((after[0] if after else as_of) - before[-1]) <= timedelta(hours=rules.travel_max_gap_hours)
            if gap_ok:
                rows.append(DayRow(D, "TRAVEL_BRIDGED", 0, streak, SUMMARY["TRAVEL_BRIDGED"], ACTION["TRAVEL_BRIDGED"], notes, ev))
                D += timedelta(days=1)
                continue

        def missed_code() -> str:
            rej = rejected_by_claim.get(D, [])
            if rej:
                order = ["REJECTED_UNPUBLISHED", "REJECTED_QUEUE_MISMATCH", "REJECTED_TOO_OLD", "REJECTED_CAP"]
                top = sorted(rej, key=lambda l: order.index(l.trust) if l.trust in order else 9)[0]
                return "MISSED_BACKDATE_" + top.trust.replace("REJECTED_", "")
            if ls:
                return "MISSED_SWIPE_ONLY" if swipe_only else "MISSED_BELOW_THRESHOLD"
            if orphan_days.get(D):
                return "MISSED_START_ONLY"
            return "MISSED_NO_ACTIVITY"

        # nothing to protect: no streak is alive, so never park a day as pending and never burn a freeze on it
        if streak == 0:
            code = missed_code()
            rows.append(DayRow(D, code, 0, 0, SUMMARY[code], ACTION[code], notes, ev))
            D += timedelta(days=1)
            continue

        # ---- missed day lifecycle
        final_at = t0 + timedelta(hours=rules.pending_hours)
        recent_open = [o for o in live_opens if d_start <= o.rx <= as_of]
        if recent_open and (recent_open[-1].queue_depth or 0) > 0:        # device still holds unsynced events
            final_at = max(final_at, t0 + timedelta(hours=rules.max_offline_delay_hours))
        confirmed_at = next((o.rx for o in live_opens if o.rx >= t0 and o.queue_depth == 0 and o.rx <= as_of), None)
        cutoff = min(as_of, final_at)
        tokens = tokens_base + sum(1 for p in purchases if p.rx <= cutoff) - consumed
        auto_at = confirmed_at if confirmed_at else t0 + timedelta(hours=rules.auto_freeze_after_hours)
        if confirmed_at and confirmed_at > t0 + timedelta(hours=rules.auto_freeze_after_hours):
            auto_at = t0 + timedelta(hours=rules.auto_freeze_after_hours)
        if tokens > 0 and as_of >= auto_at:
            consumed += 1
            rows.append(DayRow(D, "FREEZE_USED", 0, streak, SUMMARY["FREEZE_USED"], ACTION["FREEZE_USED"], notes, ev))
            D += timedelta(days=1)
            continue
        if as_of < final_at:
            code = "PENDING_FREEZE_OFFER" if (confirmed_at and tokens <= 0) else "PENDING_SYNC"
            if pending_first_streak is None:
                pending_first_streak, since_pending = streak, 0
            pending_final_at = pending_final_at or final_at
            r = DayRow(D, code, 0, streak, SUMMARY[code], ACTION[code], notes, ev, final=False)
            r.evidence["final_at_utc"] = final_at.strftime("%Y-%m-%d %H:%M")
            rows.append(r)
            D += timedelta(days=1)
            continue

        # ---- final miss: the streak ends here
        code = missed_code()
        broken_on = D
        breaks.append((D, code, streak))
        rows.append(DayRow(D, code, 0, 0, SUMMARY[code], ACTION[code], notes, ev))
        streak = 0
        pending_first_streak = None
        D += timedelta(days=1)

    # freeze applied for a date that turned out learned -> not consumed, refund candidate
    refunds = []
    by_date = {r.day: r for r in rows}
    for a in applied:
        fd = a.meta.get("for_date")
        if not fd:
            continue
        try:
            r = by_date.get(date.fromisoformat(fd))
        except ValueError:
            continue
        if r and r.code.startswith("LEARNED"):
            order = next((p.meta.get("order") for p in purchases if abs((p.rx - a.rx).total_seconds()) < 600), None)
            r.notes.append("a Freeze was applied for this date but the lesson synced afterwards: Freeze NOT consumed, refund/return it")
            refunds.append({"date": fd, "order": order, "amount_inr": rules.freeze_price_inr,
                            "reason": "freeze bought/applied for a day that was actually learned (late sync)"})

    # ---- headline status
    last = rows[-1] if rows else None
    today_row = by_date.get(today)
    pending_rows = [r for r in rows if r.code.startswith("PENDING")]
    if pending_rows:                                   # an unresolved day matters more than today's tick
        status = "PENDING"
    elif today_row and today_row.code.startswith("LEARNED"):
        status = "SAFE_TODAY"
    elif streak > 0:
        status = "AT_RISK"
    else:
        status = "BROKEN"

    protected = [r for r in rows if r.code in ("OUTAGE_PROTECTED", "TRAVEL_BRIDGED", "FREEZE_USED")]
    reason = _reason(status, streak, rows, protected, breaks, last_learned_day, pending_rows, pending_final_at)
    tokens_end = tokens_base + sum(1 for p in purchases if p.rx <= as_of) - consumed
    return UserResult(user=user, as_of=as_of, today=today, tz=tz_now, streak=streak, status=status, reason=reason,
                      rows=rows if from_day is None else [r for r in rows if r.day >= from_day],
                      streak_if_pending_missed=(since_pending if pending_first_streak is not None else None),
                      freeze_tokens=tokens_end, refund_candidates=refunds, pending_final_at=pending_final_at,
                      broken_on=broken_on, rules_used={})


def _reason(status, streak, rows, protected, breaks, last_learned, pending_rows, pending_final_at) -> str:
    bits = []
    if status == "SAFE_TODAY":
        bits.append(f"Learned today; {streak}-day streak.")
    elif status == "PENDING":
        p = pending_rows[0]
        bits.append(f"{streak}-day streak shown, but {p.day.isoformat()} is unresolved ({p.code}); "
                    f"it is settled by {pending_final_at.strftime('%d %b %H:%M UTC') if pending_final_at else 'the end of the window'}.")
    elif status == "AT_RISK":
        bits.append(f"{streak}-day streak through {last_learned.isoformat() if last_learned else 'baseline'}; today's lesson is still due.")
    else:
        bits.append("No active streak.")
    if protected:
        kinds = {}
        for r in protected:
            kinds.setdefault(r.code, []).append(r.day.strftime("%d %b"))
        pretty = {"OUTAGE_PROTECTED": "outage", "TRAVEL_BRIDGED": "travel date-skip", "FREEZE_USED": "freeze"}
        bits.append("Protected (adds 0): " + "; ".join(f"{pretty[k]} {', '.join(v)}" for k, v in kinds.items()) + ".")
    if breaks:
        day, code, lost = breaks[-1]
        more = sum(1 for r in rows if r.code == code and r.day > day)
        bits.append(f"A {lost}-day streak ended {day.strftime('%d %b')}: {code}" + (f" (same on {more} more day{'s' if more > 1 else ''})" if more else "") + ".")
    return " ".join(bits)
