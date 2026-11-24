# Jumpp streaks-v2

Python 3.10+ and one tiny package for the timezone database. **On Windows run this first:**
```bash
python -m pip install tzdata        # or: python -m pip install -r requirements.txt
```
(Mac/Linux already have it. If you forget, the app now tells you exactly this instead of crashing.)

## Run in under 2 minutes
```bash
python -m unittest discover -s tests -t .        # 40 tests, ~1 s
python -m streaks csv                            # regenerates streaks_as_of_2026-11-15T1000IST.csv
python -m streaks serve                          # http://127.0.0.1:8080  (seeds from ./data, in-memory)
```
Open **http://127.0.0.1:8080/support** (all users) or `/support/u06` (one user, per-day reason + what to do).

## API
```bash
curl 'localhost:8080/users/u08/streak?as_of=2026-11-15T10:00:00%2B05:30'
curl 'localhost:8080/users/u08/days?from=2026-11-08&to=2026-11-10'
curl 'localhost:8080/users/u08/missed-day'        # pending days, freeze offer/price, hour-by-hour playbook
curl 'localhost:8080/users/u12/reminders'         # today's 'save your streak' pushes, in the user's own evening
curl -X POST localhost:8080/events -d '{"events":[{"event_id":"e1","user_id":"u12","event_type":"app_open",
  "client_ts":"2026-11-15T09:00:00+05:30","device_tz":"Asia/Kolkata","app_version":"3.2.0",
  "meta":"queue_depth=0","received_at":"2026-11-15T03:30:00Z"}]}'
```
* `POST /events` takes one event, a list, or `{"events": [...]}`; idempotent; safe for late/duplicate/out-of-order events.
* **Replay/backfill:** `received_at` is honoured by default (`--strict-received-at` turns that off for production). Events POSTed with a later `received_at` move the default "now" forward; without `as_of`, "now" is 15 Nov 10:00 IST until then.
* Only events with `received_at <= as_of` are visible (so `as_of` is a true time machine).
* Override the offline limit per run: `python -m streaks serve --max-offline-hours 36` (or edit `streaks/config.py`).

## Layout
`streaks/config.py` all rules | `engine.py` pure streak logic | `store.py` idempotent SQLite | `missed_day.py` hour-by-hour policy | `api.py`, `support_view.py`, `cli.py` | `tests/` | `scripts/` beta and economics maths | `data/` inputs (+ incident window and affected uids)

## Reason codes (one per day)
`LEARNED`, `LEARNED_LATE_VERIFIED`, `LEARNED_LATE_UNVERIFIED`, `OUTAGE_PROTECTED`, `TRAVEL_BRIDGED`, `FREEZE_USED`, `PENDING_SYNC`, `PENDING_FREEZE_OFFER`, `TODAY_OPEN`, `MISSED_NO_ACTIVITY`, `MISSED_SWIPE_ONLY`, `MISSED_BELOW_THRESHOLD`, `MISSED_START_ONLY`, `MISSED_BACKDATE_{UNPUBLISHED,QUEUE_MISMATCH,TOO_OLD,CAP}`.
Statuses: `SAFE_TODAY`, `AT_RISK`, `PENDING`, `BROKEN`.

## Notes
* `events.csv` has 5 u02 events received at 10:31-10:33 IST, *after* the 10:00 snapshot; they are ignored at the snapshot.
* The outage list uses the 4 uids in the incident's log sample (`data/incident_2026-11-09_affected_uids.csv`); production would load the full `affected_uids` table.
* Scale notes: DECISIONS.md section 6.
