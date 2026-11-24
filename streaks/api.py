"""Zero-dependency HTTP API (stdlib http.server).

POST /events                       one event, a JSON list, or {"events": [...]}; idempotent; late/duplicate safe
GET  /users/{id}/streak?as_of=     current streak, status, one-line reason
GET  /users/{id}/days?from=&to=    one row per day with a reason code (+ evidence)
GET  /users/{id}/missed-day        pending days, freeze offer/price, hour-by-hour playbook
GET  /users/{id}/reminders         today's 'save your streak' pushes (Duolingo-style), if any are still due
GET  /support[/ {id}]              HTML support view
GET  /health
"""
from __future__ import annotations

import json
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .models import parse_dt
from .service import Service
from .support_view import render_index, render_user


def make_handler(svc: Service):
    class H(BaseHTTPRequestHandler):
        server_version = "jumpp-streaks/2"

        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body, ctype="application/json"):
            data = body.encode() if isinstance(body, str) else json.dumps(body, indent=2, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _as_of(self, q):
            v = q.get("as_of", [None])[0]
            if not v:
                return None
            try:
                return parse_dt(v)
            except Exception:
                raise ValueError(f"bad as_of: {v}")

        def do_POST(self):
            try:
                p = urlparse(self.path).path.rstrip("/")
                if p != "/events":
                    return self._send(404, {"error": "not found"})
                n = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(n) or b"null")
                if isinstance(payload, dict) and "events" in payload:
                    payload = payload["events"]
                if isinstance(payload, dict):
                    payload = [payload]
                if not isinstance(payload, list):
                    return self._send(400, {"error": "body must be an event, a list, or {events: [...]}"})
                res = svc.store.add_events(payload, allow_received_at=svc.allow_received_at, advance_clock=True)
                self._send(207 if res["rejected"] and res["accepted"] else (400 if res["rejected"] else 200), res)
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid JSON"})
            except Exception as e:  # never leak a stack trace
                self._send(500, {"error": str(e)})

        def do_GET(self):
            try:
                u = urlparse(self.path)
                q = parse_qs(u.query)
                parts = [x for x in u.path.split("/") if x]
                if parts == ["health"]:
                    return self._send(200, {"ok": True, "events": svc.store.count_events(), "now": svc.default_as_of().isoformat()})
                if parts[:1] == ["support"]:
                    as_of = self._as_of(q)
                    if len(parts) == 1:
                        rows = []
                        for uid in svc.store.user_ids():
                            r = svc.result(uid, as_of)
                            rows.append((uid, r.user.name, r.streak, r.status, r.reason))
                        return self._send(200, render_index(rows), "text/html")
                    r = svc.result(parts[1], as_of)
                    return self._send(404, {"error": "unknown user"}) if r is None else self._send(200, render_user(r), "text/html")
                if len(parts) == 3 and parts[0] == "users":
                    as_of = self._as_of(q)
                    frm = date.fromisoformat(q["from"][0]) if "from" in q else None
                    to = date.fromisoformat(q["to"][0]) if "to" in q else None
                    res = svc.result(parts[1], as_of, frm)
                    if res is None:
                        return self._send(404, {"error": "unknown user"})
                    if parts[2] == "streak":
                        return self._send(200, svc.streak_json(res))
                    if parts[2] == "days":
                        days = svc.days_json(res)
                        if to:
                            days = [d for d in days if d["date"] <= to.isoformat()]
                        return self._send(200, {"user_id": parts[1], "as_of": res.as_of.isoformat(), "days": days})
                    if parts[2] == "reminders":
                        return self._send(200, svc.reminders_json(parts[1], as_of))
                    if parts[2] == "missed-day":
                        return self._send(200, svc.missed_day_json(res))
                return self._send(404, {"error": "not found"})
            except (ValueError, KeyError) as e:
                self._send(400, {"error": str(e)})
            except Exception as e:
                self._send(500, {"error": str(e)})

    return H


def serve(svc: Service, host="127.0.0.1", port=8080) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(svc))
