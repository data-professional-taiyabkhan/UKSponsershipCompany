"""Seed a baseline from a register CSV you already have on disk.

Use this once, to backdate the history with any older copy of the register you
kept. Everything after that comes from fetch_register.py.

    python snapshot/seed_baseline.py path/to/register.csv 2026-09-04
"""
from __future__ import annotations

import sys
from datetime import datetime

import pandas as pd

from lib import canonical, write_baseline


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    path, day = sys.argv[1], sys.argv[2]
    datetime.strptime(day, "%Y-%m-%d")  # validate

    df = pd.read_csv(path, keep_default_na=False, dtype=str)
    curr = canonical(df)
    out = write_baseline(curr, day)
    print(f"seeded {day}: {len(curr):,} licence rows · "
          f"{curr['name_key'].nunique():,} organisations -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
