"""SQLite event store. Idempotent, and independent of arrival order.

* Primary key is (event_id, payload_hash): the same event re-sent is a no-op; the *earliest*
  received_at wins (MIN), whichever order the copies arrive in.
* Different payloads that reuse an event_id are kept side by side (nothing is silently lost);
  semantic de-duplication happens at read time in engine.dedupe().
"""
from __future__ import annotations

import csv
import hashlib
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models import Ev, Incident, User, Video, UTC, parse_dt, parse_meta

EVENT_TYPES = {"app_open", "video_start", "video_end", "tz_change", "freeze_purchase", "freeze_applied"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS events(
  event_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
  user_id TEXT NOT NULL, event_type TEXT NOT NULL, video_id TEXT, watched_s INTEGER,
  client_ts TEXT NOT NULL, device_tz TEXT NOT NULL, received_us INTEGER NOT NULL,
  app_version TEXT, meta TEXT,
  PRIMARY KEY(event_id, payload_hash)
);
CREATE INDEX IF NOT EXISTS ix_events_user_rx ON events(user_id, received_us);
CREATE TABLE IF NOT EXISTS users(user_id TEXT PRIMARY KEY, name TEXT, signup_at TEXT, home_tz TEXT,
  plan TEXT, freeze_balance INTEGER, streak_baseline INTEGER);
CREATE TABLE IF NOT EXISTS videos(video_id TEXT PRIMARY KEY, title TEXT, duration_s INTEGER, published_at TEXT);
CREATE TABLE IF NOT EXISTS incidents(incident_id TEXT PRIMARY KEY, start_utc TEXT, end_utc TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS incident_users(incident_id TEXT, user_id TEXT, PRIMARY KEY(incident_id, user_id));
"""


def _us(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000)


def _from_us(us: int) -> datetime:
    return datetime.fromtimestamp(us / 1_000_000, tz=UTC)


class ValidationError(ValueError):
    pass


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.clock_floor_us: Optional[int] = None     # advanced only by events POSTed at runtime, not by seed data
        with self.lock:
            self.db.executescript(SCHEMA)

    # ---------------------------------------------------------------- events
    @staticmethod
    def _normalise(raw: dict, now: Optional[datetime] = None, allow_received_at: bool = True) -> dict:
        for k in ("event_id", "user_id", "event_type", "client_ts", "device_tz"):
            if not raw.get(k):
                raise ValidationError(f"missing field: {k}")
        if raw["event_type"] not in EVENT_TYPES:
            raise ValidationError(f"unknown event_type: {raw['event_type']}")
        try:
            client = parse_dt(str(raw["client_ts"]), raw["device_tz"])
        except Exception:
            raise ValidationError(f"bad client_ts: {raw['client_ts']}")
        rx_raw = raw.get("received_at")
        if rx_raw and allow_received_at:
            try:
                rx = parse_dt(str(rx_raw))
            except Exception:
                raise ValidationError(f"bad received_at: {rx_raw}")
        else:
            rx = now or datetime.now(UTC)
        watched = raw.get("watched_s")
        watched = None if watched in (None, "", "nan") else int(float(watched))
        if raw["event_type"] == "video_end" and (watched is None or watched < 0):
            raise ValidationError("video_end needs watched_s >= 0")
        meta = raw.get("meta") or ""
        if isinstance(meta, dict):
            meta = ";".join(f"{k}={v}" for k, v in sorted(meta.items()))
        video = raw.get("video_id") or None
        if raw["event_type"] in ("video_start", "video_end") and not video:
            raise ValidationError("video events need video_id")
        payload = "|".join(str(x) for x in (raw["user_id"], raw["event_type"], video or "", watched if watched is not None else "",
                                              str(raw["client_ts"]), raw["device_tz"], raw.get("app_version") or "", meta))
        return dict(event_id=str(raw["event_id"]), payload_hash=hashlib.sha1(payload.encode()).hexdigest()[:16],
                    user_id=raw["user_id"], event_type=raw["event_type"], video_id=video, watched_s=watched,
                    client_ts=str(raw["client_ts"]), device_tz=raw["device_tz"], received_us=_us(rx),
                    app_version=raw.get("app_version") or "", meta=meta)

    def add_events(self, raws: Iterable[dict], allow_received_at: bool = True, now: Optional[datetime] = None,
                   advance_clock: bool = False) -> dict:
        rows, errors = [], []
        for i, raw in enumerate(raws):
            try:
                rows.append(self._normalise(raw, now=now, allow_received_at=allow_received_at))
            except ValidationError as e:
                errors.append({"index": i, "event_id": raw.get("event_id"), "error": str(e)})
        new = dup = 0
        with self.lock:
            for r in rows:
                cur = self.db.execute("SELECT received_us FROM events WHERE event_id=? AND payload_hash=?",
                                      (r["event_id"], r["payload_hash"])).fetchone()
                if cur is None:
                    self.db.execute(
                        "INSERT INTO events VALUES(:event_id,:payload_hash,:user_id,:event_type,:video_id,:watched_s,"
                        ":client_ts,:device_tz,:received_us,:app_version,:meta)", r)
                    new += 1
                else:
                    dup += 1
                    if r["received_us"] < cur["received_us"]:      # earliest receipt wins, order-independent
                        self.db.execute("UPDATE events SET received_us=? WHERE event_id=? AND payload_hash=?",
                                        (r["received_us"], r["event_id"], r["payload_hash"]))
            self.db.commit()
            if advance_clock and rows:
                self.clock_floor_us = max(self.clock_floor_us or 0, max(r["received_us"] for r in rows))
        return {"accepted": new, "duplicates": dup, "rejected": errors}

    def user_events(self, user_id: str, as_of: datetime) -> list[Ev]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM events WHERE user_id=? AND received_us<=?",
                                   (user_id, _us(as_of))).fetchall()
        out = []
        for r in rows:
            out.append(Ev(r["event_id"], r["user_id"], r["event_type"], r["video_id"], r["watched_s"],
                          parse_dt(r["client_ts"], r["device_tz"]), r["device_tz"], _from_us(r["received_us"]),
                          r["app_version"] or "", parse_meta(r["meta"])))
        return out

    def clock_floor(self) -> Optional[datetime]:
        return _from_us(self.clock_floor_us) if self.clock_floor_us else None

    def max_received(self) -> Optional[datetime]:
        with self.lock:
            r = self.db.execute("SELECT MAX(received_us) m FROM events").fetchone()
        return _from_us(r["m"]) if r and r["m"] is not None else None

    def count_events(self) -> int:
        with self.lock:
            return self.db.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]

    # ------------------------------------------------------------ reference data
    def user(self, user_id: str) -> Optional[User]:
        with self.lock:
            r = self.db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not r:
            return None
        return User(r["user_id"], r["name"], parse_dt(r["signup_at"]), r["home_tz"], r["plan"],
                    int(r["freeze_balance"]), int(r["streak_baseline"]))

    def user_ids(self) -> list[str]:
        with self.lock:
            return [r["user_id"] for r in self.db.execute("SELECT user_id FROM users ORDER BY user_id")]

    def videos(self) -> dict[str, Video]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM videos").fetchall()
        return {r["video_id"]: Video(r["video_id"], r["title"], int(r["duration_s"]), parse_dt(r["published_at"])) for r in rows}

    def incidents(self) -> list[Incident]:
        with self.lock:
            inc = self.db.execute("SELECT * FROM incidents").fetchall()
            users = self.db.execute("SELECT * FROM incident_users").fetchall()
        by = {}
        for u in users:
            by.setdefault(u["incident_id"], set()).add(u["user_id"])
        return [Incident(i["incident_id"], parse_dt(i["start_utc"]), parse_dt(i["end_utc"]), i["description"],
                         frozenset(by.get(i["incident_id"], ()))) for i in inc]

    # -------------------------------------------------------------------- seeding
    def seed(self, data_dir: str | Path) -> dict:
        d = Path(data_dir)
        with self.lock:
            for r in csv.DictReader(open(d / "users.csv", newline="")):
                self.db.execute("INSERT OR REPLACE INTO users VALUES(?,?,?,?,?,?,?)",
                                (r["user_id"], r["name"], r["signup_at"], r["home_tz"], r["plan"],
                                 int(r["freeze_balance"]), int(r["streak_as_of_2026_10_31"])))
            for r in csv.DictReader(open(d / "videos.csv", newline="")):
                self.db.execute("INSERT OR REPLACE INTO videos VALUES(?,?,?,?)",
                                (r["video_id"], r["title"], int(r["duration_s"]), r["published_at"]))
            inc_f = d / "incidents.csv"
            if inc_f.exists():
                for r in csv.DictReader(open(inc_f, newline="")):
                    self.db.execute("INSERT OR REPLACE INTO incidents VALUES(?,?,?,?)",
                                    (r["incident_id"], r["start_utc"], r["end_utc"], r["description"]))
            aff = d / "incident_2026-11-09_affected_uids.csv"
            if aff.exists():
                for r in csv.DictReader(open(aff, newline="")):
                    self.db.execute("INSERT OR IGNORE INTO incident_users VALUES(?,?)", ("inc_2026_11_09", r["uid"]))
            self.db.commit()
        raws = list(csv.DictReader(open(d / "events.csv", newline="")))
        return self.add_events(raws)
