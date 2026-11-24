import json
import threading
import unittest
import urllib.request
from urllib.error import HTTPError

from streaks.api import serve
from tests.helpers import seeded


def call(base, path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode(), r.headers.get_content_type()
    except HTTPError as e:
        return e.code, e.read().decode(), "application/json"


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc = seeded(); cls.srv = serve(cls.svc, "127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_streak_and_days(self):
        st, b, _ = call(self.base, "/users/u08/streak?as_of=2026-11-15T10:00:00%2B05:30")
        j = json.loads(b); self.assertEqual((st, j["current_streak"], j["status"]), (200, 313, "AT_RISK"))
        st, b, _ = call(self.base, "/users/u08/days?from=2026-11-08&to=2026-11-10&as_of=2026-11-15T10:00:00%2B05:30")
        self.assertEqual([d["code"] for d in json.loads(b)["days"]], ["LEARNED", "OUTAGE_PROTECTED", "LEARNED"])

    def test_post_late_event_changes_answer_and_is_idempotent(self):
        ev = lambda t, ts, rx, **k: dict(event_id=f"api_{t}", user_id="u12", event_type=t, client_ts=ts, device_tz="Asia/Kolkata",
                                         received_at=rx, app_version="3.2.0", **k)
        batch = [ev("app_open", "2026-11-05T20:00:00+05:30", "2026-11-06T09:30:00Z", meta="queue_depth=0"),
                 ev("video_start", "2026-11-05T20:00:05+05:30", "2026-11-06T09:30:01Z", video_id="v001"),
                 ev("video_end", "2026-11-05T20:02:30+05:30", "2026-11-06T09:30:02Z", video_id="v001", watched_s=140)]
        # a reconnect open that proves 3 events were queued
        pre = [dict(event_id="api_pre", user_id="u12", event_type="app_open", client_ts="2026-11-06T15:00:00+05:30",
                    device_tz="Asia/Kolkata", received_at="2026-11-06T09:29:50Z", app_version="3.2.0", meta="queue_depth=3")]
        self.assertEqual(call(self.base, "/events", pre + batch)[0], 200)
        s1 = json.loads(call(self.base, "/events", pre + batch)[1]); self.assertEqual(s1["accepted"], 0)
        j = json.loads(call(self.base, "/users/u12/streak?as_of=2026-11-15T10:00:00%2B05:30")[1])
        self.assertEqual(j["current_streak"], 15 + 14)     # 5 Nov restored by a verified late sync: 15 baseline + 14 days

    def test_validation_and_404(self):
        self.assertEqual(call(self.base, "/events", {"event_id": "z"})[0], 400)
        self.assertEqual(call(self.base, "/users/nope/streak")[0], 404)
        self.assertEqual(call(self.base, "/users/u01/streak?as_of=garbage")[0], 400)

    def test_support_view_is_html(self):
        st, b, ct = call(self.base, "/support/u07")
        self.assertEqual((st, ct), (200, "text/html")); self.assertIn("REFUND Rs 49", b)


if __name__ == "__main__":
    unittest.main()
