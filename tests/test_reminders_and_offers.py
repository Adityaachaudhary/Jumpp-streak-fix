import unittest
from datetime import datetime

from streaks.models import parse_dt
from tests.helpers import blank, ev, lesson, seeded, streak


class Reminders(unittest.TestCase):
    def test_not_learned_yet_gets_three_escalating_reminders_in_user_local_evening(self):
        s = seeded()
        j = s.reminders_json("u12", parse_dt("2026-11-15T10:00:00+05:30"))
        self.assertEqual([r["kind"] for r in j["reminders"]], ["usual_time", "evening", "final"])
        self.assertTrue(all(r["send_at_local"] < "2026-11-15 23:59" for r in j["reminders"]))
        self.assertIn("9-day streak", j["reminders"][1]["title"])

    def test_no_reminder_after_learning_today(self):
        s = seeded()
        j = s.reminders_json("u12", parse_dt("2026-11-14T22:00:00+05:30"))      # u12 already learned on 14 Nov
        self.assertEqual(j["reminders"], []); self.assertEqual(j["suppressed"], "already learned today")

    def test_reminders_use_the_users_own_timezone(self):
        s = seeded()
        j = s.reminders_json("u02", parse_dt("2026-11-15T10:00:00+05:30"))     # u02 is in San Francisco: still 14 Nov there
        self.assertEqual(j["tz"], "America/Los_Angeles"); self.assertEqual(j["local_today"], "2026-11-14")
        self.assertTrue(j["reminders"][0]["send_at_local"].startswith("2026-11-14"))

    def test_no_nagging_when_a_lesson_is_waiting_to_sync(self):
        s = blank(); s.store.add_events(lesson("2026-11-01T08:00:00"))
        s.store.add_events([ev("app_open", "2026-11-02T12:00:00+05:30", meta="queue_depth=3")])   # 3 events unsynced today
        j = s.reminders_json("x", parse_dt("2026-11-02T18:00:00+05:30"))
        self.assertIn("unsynced", j["suppressed"])

    def test_passed_slots_are_dropped(self):
        s = blank(); s.store.add_events(lesson("2026-11-01T08:00:00"))
        j = s.reminders_json("x", parse_dt("2026-11-02T22:00:00+05:30"))        # only the 22:30 final is left
        self.assertEqual([r["kind"] for r in j["reminders"]], ["final"])


class FreezeOffer(unittest.TestCase):
    def test_new_free_user_gets_free_freezes_then_pays(self):
        s = blank(); s.store.db.execute("UPDATE users SET signup_at='2026-10-25T00:00:00+05:30'"); s.store.db.commit()
        s.store.add_events(lesson("2026-11-01T08:00:00"))
        o = s.missed_day_json(streak(s, "2026-11-03T10:00:00+05:30"))["freeze_offer"]
        self.assertEqual((o["price_inr"], o["free_remaining"]), (0, 2))

    def test_existing_free_user_pays_full_price(self):
        s = blank(); s.store.add_events(lesson("2026-11-01T08:00:00"))          # signed up 1 Sep: not new
        o = s.missed_day_json(streak(s, "2026-11-03T10:00:00+05:30"))["freeze_offer"]
        self.assertEqual((o["price_inr"], o["free_remaining"]), (49, 0))


if __name__ == "__main__":
    unittest.main()
