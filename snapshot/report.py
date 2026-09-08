"""Summarise what changed on the register over the last N days.

This is the weekly-post generator: newly licensed sponsors are the highest
signal in the dataset, because a company that has just paid for a licence is a
company that intends to use it.

Usage:
    python snapshot/report.py --days 7
    python snapshot/report.py --days 30 --route "Skilled Worker" --csv new.csv
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, timedelta

import pandas as pd

from lib import DIFF_DIR, NON_EXTERNAL_ROUTES


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--route", default="Skilled Worker")
    ap.add_argument("--csv", help="write the newly licensed sponsors to this path")
    args = ap.parse_args()

    since = (date.today() - timedelta(days=args.days)).isoformat()
    added, removed, ratings = [], [], []
    for path in sorted(DIFF_DIR.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        if d["date"] < since:
            continue
        added += d["added"]
        removed += d["removed"]
        ratings += d["rating_changed"]

    if not (added or removed or ratings):
        print(f"no recorded changes in the last {args.days} days "
              f"(need at least two snapshots to diff)")
        return 0

    A = pd.DataFrame(added)
    R = pd.DataFrame(removed)

    print(f"=== Register changes, last {args.days} days (since {since}) ===\n")
    print(f"  licences added    {len(A):,}")
    print(f"  licences removed  {len(R):,}")
    print(f"  rating changes    {len(ratings):,}")

    if len(A):
        route_a = A[A["route"] == args.route]
        print(f"\n--- new '{args.route}' licences: {len(route_a):,} ---")
        print("\ntop towns:")
        for town, n in Counter(route_a["town"].str.upper()).most_common(10):
            print(f"  {n:>4}  {town}")
        print("\nmost recent 15:")
        for r in route_a.tail(15).to_dict("records"):
            print(f"  {r['name'][:52]:<52}  {r['town']}")
        if args.csv:
            route_a.to_csv(args.csv, index=False)
            print(f"\nwrote {len(route_a):,} rows to {args.csv}")

    if len(R):
        print(f"\n--- removed from register: {len(R):,} ---")
        print("  NB 'removed' is not 'revoked'. It can be a surrender, an")
        print("  expiry, a merger or a rename. Never publish it as a revocation.")

    if ratings:
        print(f"\n--- rating changes: {len(ratings):,} ---")
        for r in ratings[:10]:
            print(f"  {r['name'][:44]:<44}  {r['rating_before']} -> {r['rating']}")

    skipped = sum(1 for r in added if r["route"] in NON_EXTERNAL_ROUTES)
    if skipped:
        print(f"\n({skipped} of the added licences are on routes an external "
              f"applicant cannot apply to.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
