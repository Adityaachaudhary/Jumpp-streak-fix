import unittest
from dataclasses import replace

from streaks.config import Rules
from streaks.models import parse_dt
from tests.helpers import blank, ev, lesson, seeded, streak

AS_OF = "2026-11-06T10:00:00+05:30"   # day 06 Nov morning, user x baseline 10 ending 31 Oct


def codes(res):
    return {r.day.isoformat(): r.code for r in res.rows}


class LearningDay(unittest.TestCase):
    def test_one_completed_short_lesson_counts_T8(self):
        s = blank(); s.store.add_events(lesson("2026-11-01T08:00:00", "v1", 97))   # 97% of a 100 s lesson
        self.assertEqual(codes(streak(s, AS_OF))["2026-11-01"], "LEARNED")

    def test_swipe_farming_does_not_count_T3(self):
        s = blank()
        for i, v in enumerate(["v1", "v2", "v3"]):
            s.store.add_events(lesson(f"2026-11-01T08:0{i}:00", v, 4))
        self.assertEqual(codes(streak(s, AS_OF))["2026-11-01"], "MISSED_SWIPE_ONLY")

    def test_partial_but_real_watching_adds_up(self):
        s = blank()
        s.store.add_events(lesson("2026-11-01T08:00:00", "v2", 60) + lesson("2026-11-01T08:10:00", "v3", 70))  # 50%+47% = 130 s
        self.assertEqual(codes(streak(s, AS_OF))["2026-11-01"], "LEARNED")

    def test_same_video_repeated_counts_once(self):
        s = blank()
        s.store.add_events(lesson("2026-11-01T08:00:00", "v2", 60) + lesson("2026-11-01T08:10:00", "v2", 60))  # 60 s once
        self.assertEqual(codes(streak(s, AS_OF))["2026-11-01"], "MISSED_BELOW_THRESHOLD")

    def test_start_without_end_is_not_a_lesson_u11(self):
        s = blank(); s.store.add_events(lesson("2026-11-01T08:00:00")[:2])
        self.assertEqual(codes(streak(s, AS_OF))["2026-11-01"], "MISSED_START_ONLY")


class DayBoundary(unittest.TestCase):
    def test_lesson_straddling_midnight_belongs_to_day_it_started_T4(self):
        s = blank()
        s.store.add_events([ev("app_open", "2026-11-01T23:58:40+05:30", meta="queue_depth=0"),
                            ev("video_start", "2026-11-01T23:59:05+05:30", video="v1"),
                            ev("video_end", "2026-11-02T00:00:27+05:30", video="v1", watched=98)])
        c = codes(streak(s, "2026-11-04T10:00:00+05:30"))
        self.assertEqual(c["2026-11-01"], "LEARNED")
        self.assertNotEqual(c["2026-11-02"], "LEARNED")

    def test_travel_west_does_not_break_streak_T1(self):
        r = seeded().result("u02"); c = codes(r)
        self.assertTrue(all(v == "LEARNED" for k, v in c.items() if k <= "2026-11-13"))
        self.assertEqual(r.streak, 54)

    def test_eastbound_date_skip_is_bridged_but_adds_nothing_u15(self):
        r = seeded().result("u15"); c = codes(r)
        self.assertEqual(c["2026-11-10"], "TRAVEL_BRIDGED")
        self.assertEqual(r.streak, 17 + 9 + 4)

    def test_events_after_as_of_are_invisible(self):
        s = seeded()
        self.assertEqual(s.result("u02").streak, 54)                                  # 14 Nov PT lesson arrives 10:31 IST
        self.assertEqual(s.result("u02", parse_dt("2026-11-15T11:00:00+05:30")).streak, 55)


class Outage(unittest.TestCase):
    def test_outage_day_bridges_but_adds_zero_u08(self):
        r = seeded().result("u08")
        self.assertEqual(codes(r)["2026-11-09"], "OUTAGE_PROTECTED")
        self.assertEqual(r.streak, 300 + 8 + 5)
        self.assertEqual(r.freeze_tokens, 1)               # no freeze burned

    def test_unaffected_user_gets_no_outage_protection(self):
        s = blank(); s.store.add_events(lesson("2026-11-08T08:00:00"))   # nothing on 9 Nov
        self.assertEqual(codes(streak(s, "2026-11-12T10:00:00+05:30"))["2026-11-09"], "MISSED_NO_ACTIVITY")


class Freezes(unittest.TestCase):
    def test_unneeded_freeze_is_not_consumed_and_is_refundable_u07(self):
        r = seeded().result("u07")
        self.assertEqual(codes(r)["2026-11-07"], "LEARNED_LATE_VERIFIED")
        self.assertEqual(r.streak, 58 + 14)
        self.assertEqual(r.freeze_tokens, 1)
        self.assertEqual(r.refund_candidates[0]["amount_inr"], 49)

    def test_premium_freeze_auto_used_after_24h_and_returned_if_lesson_syncs_late(self):
        s = blank(plan="premium", balance=1)
        s.store.add_events(lesson("2026-11-01T08:00:00") + lesson("2026-11-03T08:00:00", qd=3))
        r = streak(s, "2026-11-04T10:00:00+05:30")
        self.assertEqual(codes(r)["2026-11-02"], "FREEZE_USED"); self.assertEqual(r.streak, 12)
        s.store.add_events(lesson("2026-11-02T20:00:00", delay_h=30, qd=0))      # late sync arrives afterwards
        r2 = streak(s, "2026-11-04T10:00:00+05:30")
        self.assertEqual(codes(r2)["2026-11-02"][:7], "LEARNED"); self.assertEqual(r2.freeze_tokens, 1)

    def test_no_freeze_is_burned_when_there_is_no_streak(self):
        s = blank(plan="premium", balance=1, baseline=0)
        s.store.add_events(lesson("2026-11-03T08:00:00"))
        r = streak(s, "2026-11-05T10:00:00+05:30")
        self.assertEqual(r.freeze_tokens, 1)


class MissedDayLifecycle(unittest.TestCase):
    def test_pending_then_final_u12(self):
        s = seeded()
        r1 = s.result("u12", parse_dt("2026-11-06T09:00:00+05:30"))          # day after the miss
        self.assertEqual(codes(r1)["2026-11-05"][:7], "PENDING"); self.assertEqual(r1.status, "PENDING")
        self.assertEqual(r1.streak_if_pending_missed, 1)
        r2 = s.result("u12", parse_dt("2026-11-08T09:00:00+05:30"))          # >48 h after the miss day ended
        self.assertEqual(codes(r2)["2026-11-05"], "MISSED_NO_ACTIVITY"); self.assertEqual(r2.streak, 2)

    def test_empty_queue_open_confirms_miss_and_offers_freeze(self):
        s = blank(); s.store.add_events(lesson("2026-11-01T08:00:00") + lesson("2026-11-03T08:00:00"))
        self.assertEqual(codes(streak(s, "2026-11-03T09:00:00+05:30"))["2026-11-02"], "PENDING_FREEZE_OFFER")


class StreakSnapshot(unittest.TestCase):
    EXPECT = {"u01": 12, "u02": 54, "u03": 26, "u04": 0, "u05": 20, "u06": 5, "u07": 72, "u08": 313, "u09": 2, "u10": 23,
              "u11": 3, "u12": 9, "u13": 58, "u14": 65, "u15": 30}

    def test_golden_snapshot(self):
        s = seeded()
        self.assertEqual({u: s.result(u).streak for u in self.EXPECT}, self.EXPECT)

    def test_csv_file_matches_engine(self):
        import csv
        from pathlib import Path
        f = Path(__file__).resolve().parent.parent / "streaks_as_of_2026-11-15T1000IST.csv"
        got = {r["user_id"]: int(r["current_streak"]) for r in csv.DictReader(open(f))}
        self.assertEqual(got, self.EXPECT)


if __name__ == "__main__":
    unittest.main()
