import unittest
from dataclasses import replace

from streaks.config import Rules
from streaks.models import parse_dt
from tests.helpers import blank, ev, lesson, seeded, streak

AS_OF = "2026-11-06T10:00:00+05:30"


def codes(res):
    return {r.day.isoformat(): r.code for r in res.rows}


def base():
    s = blank()
    s.store.add_events(lesson("2026-11-01T08:00:00") + lesson("2026-11-03T08:00:00"))
    return s


class LateSync(unittest.TestCase):
    def test_verified_when_device_queue_matches_batch_u13_u14(self):
        r = seeded()
        for u in ("u13", "u14"):
            self.assertEqual(r.result(u).streak, {"u13": 58, "u14": 65}[u])
            self.assertIn("LEARNED_LATE_VERIFIED", {x.code for x in r.result(u).rows})

    def test_old_app_without_queue_depth_is_accepted_but_labelled_u03(self):
        self.assertIn("LEARNED_LATE_UNVERIFIED", {x.code for x in seeded().result("u03").rows})

    def test_lesson_published_after_claimed_time_is_rejected_u06(self):
        r = seeded().result("u06")
        c = codes(r)
        self.assertEqual((c["2026-11-08"], c["2026-11-09"]), ("MISSED_BACKDATE_UNPUBLISHED",) * 2)
        self.assertEqual(r.streak, 5)

    def test_queue_depth_contradiction_is_rejected(self):
        s = base()
        s.store.add_events(lesson("2026-11-02T20:00:00", delay_h=20, qd=0))     # batch of 3 arrives, device said 0 unsynced
        # reconnect open (live) with queue_depth=0 just before the batch
        s.store.add_events([ev("app_open", "2026-11-03T16:00:00+05:30", meta="queue_depth=0")])
        self.assertEqual(codes(streak(s, AS_OF))["2026-11-02"], "MISSED_BACKDATE_QUEUE_MISMATCH")

    def test_matching_queue_depth_is_verified(self):
        s = base()
        s.store.add_events([ev("app_open", "2026-11-03T16:00:00+05:30", meta="queue_depth=3")])
        s.store.add_events(lesson("2026-11-02T20:00:00", delay_h=20, qd=0))
        c = codes(streak(s, AS_OF)); self.assertEqual(c["2026-11-02"], "LEARNED_LATE_VERIFIED")

    def test_36h_limit_changes_only_u03(self):
        a, b = seeded(), seeded(replace(Rules(), max_offline_delay_hours=36))
        diff = {u: (a.result(u).streak, b.result(u).streak) for u in a.store.user_ids() if a.result(u).streak != b.result(u).streak}
        self.assertEqual(diff, {"u03": (26, 2)})

    def test_uncorroborated_cap(self):
        s = blank(); s.store.add_events(lesson("2026-11-01T08:00:00", ver="3.1.4"))
        for d in (2, 3, 4, 5):
            s.store.add_events(lesson(f"2026-11-0{d}T20:00:00", delay_h=20, ver="3.1.4"))
        c = codes(streak(s, "2026-11-08T10:00:00+05:30"))
        self.assertEqual([c[f"2026-11-0{d}"] for d in (2, 3, 4, 5)],
                         ["LEARNED_LATE_UNVERIFIED"] * 3 + ["MISSED_BACKDATE_CAP"])

    def test_future_dated_clock_is_credited_at_receipt(self):
        s = blank()
        s.store.add_events(lesson("2026-11-10T08:00:00", delay_h=-48, ver="3.2.0"))   # claims 2 days in the future
        r = streak(s, "2026-11-12T10:00:00+05:30")
        self.assertTrue(any(l["trust"] == "FUTURE_TS" for x in r.rows for l in x.evidence["lessons"]))


if __name__ == "__main__":
    unittest.main()
