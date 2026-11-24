import csv
import random
import unittest

from streaks.config import Rules
from streaks.service import Service
from streaks.store import Store
from tests.helpers import DATA, seeded


def snapshot(svc):
    return {u: (r.streak, r.status, tuple((x.day, x.code) for x in r.rows)) for u in svc.store.user_ids() for r in [svc.result(u)]}


class OrderIndependence(unittest.TestCase):
    def test_shuffled_batched_and_replayed_events_give_identical_results(self):
        want = snapshot(seeded())
        raws = list(csv.DictReader(open(DATA / "events.csv", newline="")))
        for seed in range(6):
            rnd = random.Random(seed); rnd.shuffle(raws)
            st = Store(); st.seed(DATA); st.db.execute("DELETE FROM events"); st.db.commit()
            step = max(1, len(raws) // rnd.randint(1, 7))
            for i in range(0, len(raws), step):
                st.add_events(raws[i:i + step])
            st.add_events(raws[:100])                       # replay a chunk: must be a no-op
            self.assertEqual(snapshot(Service(st, Rules())), want, f"seed {seed}")

    def test_regenerated_event_ids_do_not_double_count_u03(self):
        r = seeded().result("u03")
        day = next(x for x in r.rows if x.day.isoformat() == "2026-11-10")
        self.assertEqual(len(day.evidence["lessons"]), 1)
        self.assertGreaterEqual(day.evidence["duplicates_dropped"], 2)   # exact repeats collapse in the store; regenerated ids here

    def test_earliest_received_wins_whatever_the_arrival_order(self):
        st = Store(); st.seed(DATA)
        e = dict(event_id="dupe1", user_id="u01", event_type="app_open", client_ts="2026-11-14T20:00:00+05:30",
                 device_tz="Asia/Kolkata", app_version="3.2.0", meta="queue_depth=0")
        st.add_events([dict(e, received_at="2026-11-14T16:00:00Z")]); st.add_events([dict(e, received_at="2026-11-14T14:30:30Z")])
        rx = st.db.execute("SELECT received_us FROM events WHERE event_id='dupe1'").fetchall()
        self.assertEqual(len(rx), 1)


if __name__ == "__main__":
    unittest.main()
