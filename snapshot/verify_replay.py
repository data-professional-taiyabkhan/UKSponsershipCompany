"""Prove that baseline + diffs reconstructs the register exactly.

The storage design only works if replay is lossless. Run this after any change
to lib.py, and in CI if you ever add it.

    python snapshot/verify_replay.py path/to/todays-register.csv
    python snapshot/verify_replay.py --fetch      # download today's and check
"""
from __future__ import annotations

import io
import sys
import urllib.request

import pandas as pd

from lib import canonical, replay_state


def load_live() -> pd.DataFrame:
    from fetch_register import UA, resolve_csv_url

    url, _ = resolve_csv_url()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read()
    return pd.read_csv(io.BytesIO(raw), keep_default_na=False, dtype=str)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1

    df = load_live() if sys.argv[1] == "--fetch" else pd.read_csv(
        sys.argv[1], keep_default_na=False, dtype=str
    )
    truth = canonical(df)
    date, rebuilt = replay_state()

    print(f"replayed to {date}: {len(rebuilt):,} rows")
    print(f"source file:     {len(truth):,} rows")

    t = set(truth["key"])
    r = set(rebuilt["key"])
    missing, extra = t - r, r - t

    # ratings must match too, not just membership
    tm = truth.set_index("key")["rating"]
    rm = rebuilt.set_index("key")["rating"]
    common = list(t & r)
    mismatched = [k for k in common if tm[k] != rm[k]]

    ok = not (missing or extra or mismatched)
    print(f"missing from replay: {len(missing):,}")
    print(f"extra in replay:     {len(extra):,}")
    print(f"rating mismatches:   {len(mismatched):,}")

    if ok:
        print("\nPASS — replay is lossless")
        return 0

    for k in list(missing)[:5]:
        print(f"  missing  {k}")
    for k in list(extra)[:5]:
        print(f"  extra    {k}")
    print("\nFAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
