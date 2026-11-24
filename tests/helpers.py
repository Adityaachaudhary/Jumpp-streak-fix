from dataclasses import replace
from datetime import datetime
from pathlib import Path

from streaks.config import Rules
from streaks.models import UTC, parse_dt
from streaks.service import Service
from streaks.store import Store

DATA = Path(__file__).resolve().parent.parent / "data"


def seeded(rules: Rules | None = None) -> Service:
    st = Store()
    st.seed(DATA)
    return Service(st, rules or Rules())


def blank(rules: Rules | None = None, plan="free", baseline=10, home_tz="Asia/Kolkata", balance=0) -> Service:
    """Empty service with one synthetic user 'x' (signed up long ago) and a few videos."""
    st = Store()
    st.db.execute("INSERT INTO users VALUES('x','X','2026-09-01T00:00:00+05:30',?,?,?,?)", (home_tz, plan, balance, baseline))
    for i, (dur, pub) in enumerate([(100, "2026-10-01"), (120, "2026-10-01"), (150, "2026-10-01"), (90, "2026-11-10")], 1):
        st.db.execute("INSERT INTO videos VALUES(?,?,?,?)", (f"v{i}", f"t{i}", dur, pub + "T06:00:00+05:30"))
    st.db.commit()
    return Service(st, rules or Rules())


_n = [0]


def ev(typ, client, rx=None, video=None, watched=None, tz="Asia/Kolkata", meta="", ver="3.2.0", user="x", eid=None):
    _n[0] += 1
    return {"event_id": eid or f"t{_n[0]}", "user_id": user, "event_type": typ, "video_id": video, "watched_s": watched,
            "client_ts": client, "device_tz": tz, "received_at": rx or client, "app_version": ver, "meta": meta}


def lesson(day_ts, video="v1", watched=95, delay_h=0.0, tz_off="+05:30", tz="Asia/Kolkata", qd=0, ver="3.2.0", open_rx=None):
    """3 events: open, start, end at day_ts (e.g. '2026-11-03T08:00:00'). rx = client + delay."""
    from datetime import timedelta
    t = datetime.fromisoformat(day_ts + tz_off)
    def r(sec):
        return (t + timedelta(seconds=sec, hours=delay_h)).astimezone(UTC).isoformat().replace("+00:00", "Z")
    def c(sec):
        return (t + timedelta(seconds=sec)).isoformat()
    return [ev("app_open", c(0), r(0), tz=tz, meta=f"queue_depth={qd}", ver=ver),
            ev("video_start", c(4), r(4), video, None, tz, ver=ver),
            ev("video_end", c(100), r(100), video, watched, tz, ver=ver)]


def streak(svc, as_of, uid="x"):
    r = svc.result(uid, parse_dt(as_of))
    return r
