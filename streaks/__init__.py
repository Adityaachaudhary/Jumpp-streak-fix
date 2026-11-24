"""Jumpp streaks-v2: a small, deterministic, order-independent streak service."""
try:
    from zoneinfo import ZoneInfo as _Z
    _Z("Asia/Kolkata")
except Exception:  # Windows ships no timezone database
    raise SystemExit(
        "\nMissing timezone database (common on Windows).\n"
        "Fix:  python -m pip install tzdata      (or: python -m pip install -r requirements.txt)\n")
