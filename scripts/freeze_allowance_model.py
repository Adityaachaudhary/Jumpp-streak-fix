"""What does 'give N free freezes, then charge' cost? Rough, built only from numbers in the pack.
Run: python scripts/freeze_allowance_model.py"""
PRICE = 49
FREEZE_REV = 45e5                                    # Rs/month (economics.md)
buyers_per_month = FREEZE_REV / PRICE
rate_14d = 0.0418                                    # control freezes per enrolled user in 14 days (beta, weeks 1-4 ~ 41.8/1000)
per_user_quarter = rate_14d * (91 / 14)              # ~0.27 freezes a user would buy in a quarter
print(f"~{buyers_per_month:,.0f} paid freezes/month today (Rs 45L)")
print("\nA) Give EVERY existing user N free freezes (no grandfathering): upper bound, revenue is ~0 until the allowance is used up")
for n in (1, 3, 5):
    print(f"   N={n}: up to Rs {FREEZE_REV*min(3, n)/1e5:.0f}L over the next quarter (bound, not forecast)")
print("\nB) New free users only (existing buyers untouched):")
print(f"   expected paid freezes a new user would buy in a quarter: {per_user_quarter:.2f}")
for n in (1, 3, 5):
    print(f"   N={n}: cost <= Rs {min(n, per_user_quarter)*PRICE:.0f} per new user (more freebies than ~{per_user_quarter:.1f} cost the same)")
print("\nBreak-even in retention: +1 pt of D7 on a new user is worth Rs", round(0.01 * 45, 2), "(free LTV Rs45). So a starter pack only pays if it lifts D7 by roughly cost/0.45 points -> test N=1 first.")
