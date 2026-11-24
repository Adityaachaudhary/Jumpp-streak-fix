"""Support view: plain HTML, one user, answer in ~10 seconds.
Top: verdict + what to do. Below: one row per day with a reason code and the agent action."""
from __future__ import annotations

from html import escape

from .models import UserResult

BAD = ("MISSED_", "PENDING")


def _what_to_do(res: UserResult) -> list[str]:
    todo = []
    for rf in res.refund_candidates:
        todo.append(f"REFUND Rs {rf['amount_inr']} (order {rf['order'] or 'n/a'}): Freeze bought for {rf['date']} but that day was learned (late sync).")
    seen = set()
    for r in reversed(res.rows):
        if r.code in seen or r.code in ("LEARNED", "TODAY_OPEN", "PRE_SIGNUP"):
            continue
        if r.code.startswith("LEARNED_LATE") and not r.code.endswith("UNVERIFIED"):
            continue
        seen.add(r.code)
        todo.append(f"{r.code} ({r.day.strftime('%d %b')}): {r.action}")
    if not todo:
        todo.append("Nothing wrong found. Streak is exactly what the data supports.")
    return todo


def render_user(res: UserResult, extra_note: str = "") -> str:
    u = res.user
    head = (f"<h1>{escape(u.name)} <small>({u.user_id}, {u.plan}, home tz {escape(u.home_tz)})</small></h1>"
            f"<h2>Streak {res.streak} &mdash; {res.status}</h2><p><b>{escape(res.reason)}</b></p>"
            f"<p>As of {res.as_of.isoformat()} &middot; user's local today: {res.today.isoformat()} ({escape(res.tz)}) "
            f"&middot; Freeze balance now: {res.freeze_tokens}"
            + (f" &middot; if the pending day is missed the streak becomes {res.streak_if_pending_missed}"
               if res.streak_if_pending_missed is not None else "") + "</p>")
    todo = "<h3>What to do</h3><ol>" + "".join(f"<li>{escape(t)}</li>" for t in _what_to_do(res)) + "</ol>"
    rows = []
    for r in reversed(res.rows):
        bad = r.code.startswith(BAD)
        style = ' style="background:#fff3cd"' if r.code.startswith("PENDING") else (' style="background:#f8d7da"' if bad else "")
        ev = r.evidence
        lessons = "".join(
            f"<li>{escape(str(l['video']))}: {l['watched_s']}s of {l['duration_s']}s ({int(l['ratio']*100)}%), {l['trust']}, "
            f"claimed {l['claimed_local']} local, received {l['received_utc']} UTC"
            + (f" &rarr; {escape(l['detail'])}" if l['detail'] else "") + "</li>" for l in ev.get("lessons", []) + ev.get("claims_rejected", []))
        details = (f"<details><summary>evidence</summary><ul>{lessons}</ul>"
                   f"<p>opens {ev.get('app_opens', 0)}, unfinished starts {ev.get('orphan_starts', 0)}, "
                   f"duplicates ignored {ev.get('duplicates_dropped', 0)}, credited {ev.get('credited_s', 0)}s, tz {escape(str(ev.get('tz', '')))}</p></details>"
                   if ev else "")
        notes = "".join(f"<br><i>{escape(n)}</i>" for n in r.notes)
        rows.append(f"<tr{style}><td>{r.day.isoformat()}</td><td><code>{r.code}</code></td><td>{'+1' if r.counts else '0'}</td>"
                    f"<td>{r.streak_after}</td><td>{escape(r.summary)}{notes}{details}</td><td>{escape(r.action)}</td></tr>")
    table = ("<table border='1' cellpadding='4' cellspacing='0'><tr><th>Date (user local)</th><th>Reason code</th><th>Adds</th>"
             "<th>Streak after</th><th>What happened</th><th>What to do</th></tr>" + "".join(rows) + "</table>")
    return _page(f"Support: {u.user_id}", head + todo + table + extra_note)


def render_index(rows: list[tuple]) -> str:
    body = "".join(f"<tr><td><a href='/support/{uid}'>{uid}</a></td><td>{escape(name)}</td><td>{s}</td><td>{st}</td><td>{escape(rs)}</td></tr>"
                   for uid, name, s, st, rs in rows)
    return _page("Support: all users", "<h1>Streak support</h1><table border='1' cellpadding='4' cellspacing='0'>"
                 "<tr><th>User</th><th>Name</th><th>Streak</th><th>Status</th><th>Reason</th></tr>" + body + "</table>")


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{escape(title)}</title>"
            "<style>body{font-family:sans-serif;margin:16px}small{font-weight:normal;color:#555}"
            "td{vertical-align:top}code{font-size:12px}</style></head><body>" + body + "</body></html>")
