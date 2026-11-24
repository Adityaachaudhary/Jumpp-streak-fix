"""Expected monthly Rs cost of the u13/u14 policy at 2M users, from economics.md. Run: python scripts/unverified_sync_cost.py"""
SYNCS = 3000 * 30                 # unverifiable-looking offline syncs / month
STREAK_RELEVANT = 0.60            # would break a 7+ streak
PREMIUM = 0.10
VALUE = {"free": 45, "premium": 1600}      # remaining lifetime value (Rs)
CHURN_BUMP = {"free": 0.16, "premium": 0.12}
TICKET = 0.35 * 40                 # 35% file a ticket x Rs 40
FREEZE_LOST = 0.20 * 49 + 5        # a fake sync costs a lost Freeze sale (20% x Rs49) + Rs5 integrity/support
honest_loss = (1 - PREMIUM) * (CHURN_BUMP["free"] * VALUE["free"] + TICKET) + PREMIUM * (CHURN_BUMP["premium"] * VALUE["premium"] + TICKET)
print(f"cost of wrongly rejecting one honest, streak-relevant user: Rs {honest_loss:.1f}")
print(f"cost of wrongly accepting one fake:                         Rs {FREEZE_LOST:.1f}")
for f in (0.115, 0.25):
    fakes, honest = SYNCS * f, SYNCS * (1 - f)
    reject_all = honest * STREAK_RELEVANT * honest_loss
    accept_all = fakes * FREEZE_LOST
    print(f"fake share {f:.1%}: reject-all Rs {reject_all/1e5:5.1f}L/mo   accept-all Rs {accept_all/1e5:4.1f}L/mo")
be = honest_loss * STREAK_RELEVANT / (FREEZE_LOST + honest_loss * STREAK_RELEVANT)
print(f"break-even fake share: {be:.0%}  (reject everything only if more than this share of unverifiable syncs are fake)")
