"""Re-cut beta_cohorts.csv like-for-like (same plan, enrolment weeks 5-10) and put rupees on it.
Run: python scripts/beta_analysis.py"""
import csv
from collections import defaultdict
from pathlib import Path

rows = list(csv.DictReader(open(Path(__file__).resolve().parent.parent / "data" / "beta_cohorts.csv")))
def agg(filt):
    a = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        if filt(r):
            k = (r["arm"], r["plan"])
            a[k][0] += int(r["users_enrolled"]); a[k][1] += int(r["active_day7"]); a[k][2] += int(r["freezes_bought_first_14d"])
    return a
def show(name, filt):
    a = agg(filt); print(f"\n== {name}")
    for arm in ("control", "v2"):
        u = sum(a[(arm, p)][0] for p in ("free", "premium")); d = sum(a[(arm, p)][1] for p in ("free", "premium")); f = sum(a[(arm, p)][2] for p in ("free", "premium"))
        prem = a[(arm, "premium")][0] / u
        print(f"{arm:8s} users={u:6d} premium share={prem:5.1%} D7={d/u:6.2%} freezes/1000={1000*f/u:5.1f}")
        for p in ("free", "premium"):
            x = a[(arm, p)]; print(f"   {p:8s} D7={x[1]/x[0]:6.2%} freezes/1000={1000*x[2]/x[0]:6.1f}")
    return a
w14 = show("weeks 1-4 (premium barely enrolled in v2: billing SDK bug)", lambda r: int(r["enrol_week"]) <= 4)
w510 = show("weeks 5-10 (like for like)", lambda r: int(r["enrol_week"]) >= 5)
def tot(a, arm, i): return sum(a[(arm, p)][i] for p in ("free", "premium"))
fz = lambda a, arm: tot(a, arm, 2) / tot(a, arm, 0)
d7 = lambda a, arm: tot(a, arm, 1) / tot(a, arm, 0)
drop = 1 - fz(w510, "v2") / fz(w510, "control"); lift = (d7(w510, "v2") - d7(w510, "control")) * 100
print(f"\nlike-for-like freeze purchases: {drop:.0%} lower   D7 lift: +{lift:.1f} pts")
FREEZE_REV, PT = 45e5, 2.6e5
print(f"Rs/month: retention +{lift:.1f} pts x 2.6L = +{lift*PT/1e5:.1f}L ; freeze revenue -{drop:.0%} x 45L = -{drop*FREEZE_REV/1e5:.1f}L ; net {(lift*PT-drop*FREEZE_REV)/1e5:+.1f}L")
rec = 2/3
print(f"if an early-freeze-offer recovers {rec:.0%} of the drop (ASSUMPTION to test): net {(lift*PT-drop*(1-rec)*FREEZE_REV)/1e5:+.1f}L")
