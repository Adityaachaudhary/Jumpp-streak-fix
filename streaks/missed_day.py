"""The missed day, hour by hour: what the app shows and what we send.

t0 = local midnight at the end of a day with no lesson.  "morning" = 08:30 local next day.
This is the policy table from DECISIONS.md as executable code, so product, support and
the notification service all read the same thing (GET /users/{id}/missed-day).

Design rules (they come from the thread, in order of who they protect):
  * Never send "you lost your streak" before the day is FINAL (t0 + 48 h)           (Neha)
  * Offer a Freeze at the moment of truth: first online open after t0 that reports
    queue_depth=0 (device proves nothing is waiting)  - never while queue_depth>0   (Ritika)
  * A premium user's own free Freeze is used automatically, reversibly               (Neha/Ritika)
  * A Freeze bridges, it does not add a day                                          (Ritika/Play Store)
"""
from __future__ import annotations

from .config import Rules


def freeze_offer(plan: str, freezes_used_or_granted: int, rules: Rules, is_new_user: bool = True) -> dict:
    """Price shown for a Freeze. The free allowance is for FREE users only and only counts freezes
    already used, so 'first N are free, then Rs 49' is one comparison. (Premium already gets 1/month.)"""
    if plan == "premium":
        return {"price_inr": rules.freeze_price_inr, "free_remaining": 0, "note": "premium: monthly free freeze is in balance; extra ones paid"}
    if not is_new_user:
        return {"price_inr": rules.freeze_price_inr, "free_remaining": 0, "note": "free allowance is for new users only"}
    left = max(0, rules.free_freeze_allowance - freezes_used_or_granted)
    return {"price_inr": 0 if left > 0 else rules.freeze_price_inr, "free_remaining": left}


def timeline(archetype: str, streak: int = 23, price_inr: int = 49) -> list[dict]:
    """archetype: 'unsynced' (a) | 'forgot_free' (b) | 'forgot_premium' (c)"""
    s = streak
    if archetype == "unsynced":
        return [
            {"when": "midnight", "app": f"Phone: 'Lesson saved - counts when you're online'. Flame stays lit ({s}).", "push": "none", "freeze": "not offered, not used"},
            {"when": "next morning", "app": f"Online + synced -> {s + 1} and a green tick. Still offline -> 'pending' badge, streak {s} shown.", "push": "none (never 'you lost')", "freeze": "not offered: queue_depth>0 proves a lesson is waiting"},
            {"when": "+24h", "app": "Unchanged (pending). Settings shows 'sync needed'.", "push": "neutral nudge only if still offline: 'Connect to sync your lesson'", "freeze": "not offered, not used"},
            {"when": "+48h", "app": "Still pending: window stretches to the offline limit while queue_depth>0.", "push": "none", "freeze": "not offered. After the offline limit with nothing synced: becomes a normal miss"},
        ]
    if archetype == "forgot_free":
        return [
            {"when": "midnight", "app": f"Server marks the day PENDING. If open: 'Streak at risk' (not 'missed').", "push": "none", "freeze": "not yet"},
            {"when": "next morning", "app": f"First online open with queue_depth=0 -> 'Yesterday is missed. Save your {s}-day streak with a Freeze (Rs {price_inr}; first ones free).'", "push": "09:00 same text if not opened", "freeze": f"OFFERED here (price per allowance: Rs 0 or Rs {price_inr})"},
            {"when": "+24h", "app": "Banner: 'Last chance today to save your streak'.", "push": "second and last offer", "freeze": "OFFERED again"},
            {"when": "+48h", "app": f"Streak resets to 0. Offer a fresh start.", "push": f"'Your {s}-day streak ended' (the only loss message)", "freeze": "window closed; nothing to apply"},
        ]
    if archetype == "forgot_premium":
        return [
            {"when": "midnight", "app": f"PENDING. Flame shows {s}.", "push": "none", "freeze": "not yet"},
            {"when": "next morning", "app": f"First online open with queue_depth=0 -> 'We used your free Premium Freeze. Streak safe ({s}).'", "push": "09:00 same text if not opened", "freeze": "AUTO-USED here (balance 1 -> 0); no purchase offered"},
            {"when": "+24h", "app": "If unconfirmed (never opened/offline) the Freeze is auto-used now. If a lesson syncs later it is returned.", "push": "none", "freeze": "auto-used at +24h at the latest (reversible)"},
            {"when": "+48h", "app": f"Nothing new: {s} stays, day adds 0.", "push": "none", "freeze": "none; paid Freeze offered only if there is a second miss"},
        ]
    raise ValueError(archetype)


def to_markdown(streak: int = 23) -> str:
    out = []
    for name, key in (("(a) lesson still unsynced on the phone", "unsynced"), ("(b) free user who forgot", "forgot_free"),
                      ("(c) premium user with 1 Freeze who forgot", "forgot_premium")):
        out.append(f"\n**{name}**\n\n| When | In the app | Push | Freeze |\n|---|---|---|---|")
        for r in timeline(key, streak):
            out.append(f"| {r['when']} | {r['app']} | {r['push']} | {r['freeze']} |")
    return "\n".join(out)


if __name__ == "__main__":
    print(to_markdown())
