# DECISIONS.md: streaks-v2
*Snapshot 15 Nov 2026 10:00 IST. Reproduce: `python -m streaks csv`, `python scripts/*.py`. Rules: `streaks/config.py`; one reason code per day: `streaks/engine.py`.*

## 1. Rules
| Question | Decision | Evidence |
|---|---|---|
| Learning day | One lesson watched to **>=80%** OR **>=120 s** real watching (views <25% earn 0 s; same video once). | Lessons are 75-165 s so "2 min" alone fails honest users (u10: 101/104 s). u04 swiped 2-7 s on 9 days: fails. |
| Whose day | User's **local date when the lesson started**, in the device's timezone. | u02 IST->PT: no gap. u05 started 23:59:05, so it counts on the 9th. |
| Which clock | Server `received_at`. `client_ts` only for a late sync that passes the checks below; otherwise credit at receipt. | Sameer vs Neha. |
| Late sync | Late = >15 min. Reject if >7 days, or lesson **not yet published** at claimed time. On 3.2.0 accept if last `queue_depth` >= batch size ("verified"), reject if smaller. Old app: accept "unverified", max 3 per 30 days. | u13/u14/u07 verified; u03 unverified; u06 rejected (v037 published 10 Nov, claimed 8-9 Nov; queue_depth=0 vs 6 events). |
| Duplicates | Dedupe by `event_id` and by content; earliest receipt wins, so arrival order never matters. | u03 10 Nov. |
| Freezes | Bridge, add 0. Freeze applied to a day that was learned is not consumed and is refunded (u07, Rs 49). None burned with no streak. | Ritika. |
| Outage | Affected user, no lesson: protected, adds 0, no freeze. | u08 = 313, not 314. |
| Travel | Westbound: local dates line up. Eastbound **date skipped** by a tz change (u15, lessons 27 h apart): bridged, adds 0, only if <=48 h apart. Forgetting while travelling: not forgiven. | Neha vs Ritika: Ritika on forgetting, Neha only on a calendar artefact. |
| "Now" | Only `received_at <= as_of` exists. u02's 14 Nov PT lesson arrives 10:31 IST, so u02 = **54**, 55 an hour later. | |

**Wrong if:** support reopens >2% of closed tickets on these rules, or unverified-sync users' streak lengths differ sharply from verified ones.

## 2. Unverifiable offline syncs (u13, u14): accept both
Both are 3.2.0, lesson published weeks earlier, `queue_depth=3` for a batch of exactly 3: verified. u13 = 58, u14 = 65. (`scripts/unverified_sync_cost.py`, 90,000 syncs/month, 60% streak-relevant, 10% premium.)
- Wrongly rejecting an honest user = Rs 39.7; wrongly accepting a fake = Rs 14.8.
- At 11.5% fake: reject-all **Rs 19.0 L/month** vs accept-all **Rs 1.5 L**. At 25%: **Rs 16.1 L** vs **Rs 3.3 L**. Break-even **62% fakes**.
- **Change policy if** audited fakes among corroborated syncs exceed ~30% or cap hits climb.

## 3. The missed day, hour by hour (executable: `GET /users/{id}/missed-day`)
Key signal: first online `app_open` after midnight; `queue_depth=0` proves nothing is waiting.
| | Midnight | Next morning | +24h | +48h |
|---|---|---|---|---|
| (a) lesson unsynced | Phone: "saved, counts when online". No push. | Synced: +1. Offline: "pending", streak shown. **No freeze offered.** | Pending; neutral sync nudge at most. | Stays pending up to offline limit. Never a "lost" push. |
| (b) free, forgot | PENDING, not "missed". No push. | `queue_depth=0` open: **Freeze offer #1** (Rs 0 if allowance left, else Rs 49); push 09:00. | **Offer #2** (last). | Streak resets; the only "ended" push. |
| (c) premium, 1 Freeze | PENDING. | Freeze **auto-used**. | If unconfirmed, auto-used now; returned if a lesson later syncs. | Nothing new; adds 0. |

**Ritika's 58%** is mostly mix: weeks 1-4 had **1.0% premium in v2 vs 8.9% in control**. Like-for-like (weeks 5-10) it is **-35%**. Offering on confirmed miss restores the purchase moment; I **assume** it recovers ~2/3 (to test).
**Free freezes for new users:** the first **2** Freezes are free for *new* free users (signed up <=30 days ago), then Rs 49; existing users are untouched (`free_freeze_allowance`, `new_user_window_days`; changes the price shown, not streak maths). Cost <= Rs 13 per new user per quarter; giving all existing users 3-5 would risk up to Rs 45-135 L. Test 2 vs 0 on new users.

**Reminders (Duolingo-style, `GET /users/{id}/reminders`):** if the user hasn't learned yet today, up to 3 pushes in *their* local evening: at their usual lesson time (clamped 16-20h), 21:00 "streak ends at midnight", 22:30 last call (streak >=3). Suppressed if already learned, if the phone reports unsynced events, before 08:00, or once the slot has passed. No Freeze sales in reminders; that offer belongs to the missed-day flow.

## 4. The beta: don't ship as-is
Like-for-like: D7 **+2.4 pts** (not 4.7, which is week 1 only) = **+Rs 6.2 L/month**; freezes **-35% = -Rs 15.7 L/month**; net **-Rs 9.5 L**. With the assumed recovery: ~+Rs 1 L.
**Experiment:** 3.2.x users, plan-balanced: control / v2 / v2 + offer-on-confirmed-miss. Primary: D7; also freezes per 1,000 and tickets. 4 weeks enrolment + 14 days (~36k per arm detects a 10% purchase change). **Stop if** purchases >20% below control after 2 weeks, D7 gain <+1 pt, or "streak broke" tickets rise.

## 5. Not built
1. Auto-forgiving travel/"forgot" days (revenue, product promise). 2. A 2-minute-total rule (breaks short lessons). 3. Free freezes for existing users, or Streak Repair (bounded loss, unproven gain).

## 6. Scale (2M users, not built)
- **Store:** append-only event log partitioned by `user_id`; idempotent write on `(event_id, payload_hash)`.
- **Read model:** one row per `(user, local_day)` with verdict and reason. A late event only touches days inside the offline window, so recompute at most 7 days, never full history.
- **Time-based changes:** midnight and +48 h transitions come from a timezone-bucketed scheduler ("whose midnight just passed"), not a per-request scan. Reminders, freeze offers and the support view all read the same day table.
- **Ordering and replay:** one partition per user removes ordering races; the pure engine makes backfills (outages, rule changes) a batch replay.
- **Serving and audit:** cache `GET /streak` by user and as-of bucket; store the rules version on every day row so any rule change is auditable.
