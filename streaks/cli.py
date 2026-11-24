from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from .api import serve
from .config import Rules, rules_from_env
from .models import parse_dt
from .service import Service
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


def build(args) -> Service:
    rules = rules_from_env(Rules())
    if getattr(args, "max_offline_hours", None) is not None:
        rules = replace(rules, max_offline_delay_hours=args.max_offline_hours)
    if getattr(args, "free_freeze_allowance", None) is not None:
        rules = replace(rules, free_freeze_allowance=args.free_freeze_allowance)
    store = Store(getattr(args, "db", ":memory:"))
    if not store.user_ids() or getattr(args, "reseed", False):
        store.seed(args.data)
    return Service(store, rules, allow_received_at=not getattr(args, "strict_received_at", False))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m streaks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data", default=str(ROOT / "data"))
    common.add_argument("--db", default=":memory:", help="sqlite path (default: in-memory, reseeded each start)")
    common.add_argument("--max-offline-hours", type=float, help="override the max offline delay (default 168 = 7 days)")
    common.add_argument("--free-freeze-allowance", type=int)
    s = sub.add_parser("serve", parents=[common])
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--strict-received-at", action="store_true", help="production mode: ignore client-supplied received_at")
    c = sub.add_parser("csv", parents=[common])
    c.add_argument("--as-of", default="2026-11-15T10:00:00+05:30")
    c.add_argument("--out", default=str(ROOT / "streaks_as_of_2026-11-15T1000IST.csv"))
    args = ap.parse_args(argv)
    svc = build(args)
    if args.cmd == "csv":
        Path(args.out).write_text(svc.csv_snapshot(parse_dt(args.as_of)))
        print(f"wrote {args.out}", file=sys.stderr)
        return
    srv = serve(svc, args.host, args.port)
    print(f"streaks-v2 on http://{args.host}:{args.port}  (support view: /support)  max offline delay = "
          f"{svc.rules.max_offline_delay_hours:g} h", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
