"""Fetch today's Register of licensed sponsors (workers) and store the change.

Why this exists: the Home Office republishes the register on most working days,
the asset URL contains an opaque hash that changes every publish, and there is
no official archive anywhere. The only way to own a history is to start keeping
one. Run this daily.

Usage:
    python snapshot/fetch_register.py            # normal daily run
    python snapshot/fetch_register.py --force    # re-store even if unchanged
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import urllib.request
from datetime import date, datetime, timezone

import pandas as pd

from lib import (  # noqa: E402
    SchemaChanged,
    append_manifest,
    canonical,
    compute_diff,
    last_manifest_entry,
    latest_baseline,
    replay_state,
    write_baseline,
    write_diff,
)

CONTENT_API = (
    "https://www.gov.uk/api/content/government/publications/"
    "register-of-licensed-sponsors-workers"
)
UA = "uk-sponsor-register-snapshot/1.0 (+https://github.com/data-professional-taiyabkhan/UKSponsershipCompany)"


def _get(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def resolve_csv_url() -> tuple[str, str]:
    """Ask the gov.uk Content API where today's CSV actually lives.

    Never hardcode the asset URL: the media path is an opaque 24-hex id that
    changes on every publish, and the filename convention has already changed
    once (2025-12-22_-_Worker_and_Temporary_Worker.csv ->
    SP_-_Worker_and_Temporary_Worker_Web_Register_-_2026-09-07.csv).
    """
    doc = json.loads(_get(CONTENT_API, timeout=60))
    attachments = doc.get("details", {}).get("attachments", [])
    candidates = [
        a for a in attachments
        if str(a.get("url", "")).lower().endswith(".csv")
        and "worker" in (a.get("title", "") + a.get("url", "")).lower()
        and "student" not in (a.get("title", "") + a.get("url", "")).lower()
    ]
    if not candidates:
        raise RuntimeError(
            "no worker-register CSV attachment found on the Content API response; "
            f"saw {[a.get('url') for a in attachments]}"
        )
    a = candidates[0]
    return a["url"], doc.get("public_updated_at", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="store even if the file is byte-identical to last run")
    ap.add_argument("--baseline", action="store_true",
                    help="force writing a full baseline instead of a diff")
    args = ap.parse_args()

    today = date.today().isoformat()
    url, published = resolve_csv_url()
    print(f"source   {url}")

    raw = _get(url)
    sha = hashlib.sha256(raw).hexdigest()
    print(f"sha256   {sha[:16]}…  ({len(raw):,} bytes)")

    prev_entry = last_manifest_entry()
    if prev_entry and prev_entry.get("sha256") == sha and not args.force:
        print(f"unchanged since {prev_entry['date']} — nothing to store")
        append_manifest({
            "date": today, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_url": url, "gov_published_at": published,
            "sha256": sha, "bytes": len(raw), "result": "unchanged",
        })
        return 0

    df = pd.read_csv(io.BytesIO(raw), keep_default_na=False, dtype=str)
    try:
        curr = canonical(df)
    except SchemaChanged as e:
        # Fail loudly. A silent column rename would corrupt every later diff.
        print(f"SCHEMA CHANGED: {e}", file=sys.stderr)
        append_manifest({
            "date": today, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_url": url, "sha256": sha, "result": "schema_changed",
            "error": str(e),
        })
        return 2

    print(f"parsed   {len(curr):,} licence rows · "
          f"{curr['name_key'].nunique():,} organisations · "
          f"{curr['route'].nunique()} routes")

    base_date, _ = latest_baseline()
    first_of_month = date.today().day == 1

    if base_date is None or args.baseline or first_of_month:
        path = write_baseline(curr, today)
        result = "baseline"
        print(f"baseline {path.relative_to(path.parents[2])}")
        counts = {"rows": len(curr)}
    else:
        prev_date, prev = replay_state()
        diff = compute_diff(prev, curr, today, prev_date)
        counts = diff.to_json()["counts"]
        if diff.is_empty:
            print(f"no licence changes vs {prev_date} (file bytes differed only)")
            result = "no_change"
        else:
            path = write_diff(diff)
            result = "diff"
            print(f"diff     +{counts['added']} added  "
                  f"-{counts['removed']} removed  "
                  f"~{counts['rating_changed']} rating changed  vs {prev_date}")
            for r in diff.added[:5].to_dict("records"):
                print(f"           + {r['name']} · {r['town']} · {r['route']}")

    append_manifest({
        "date": today, "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_url": url, "gov_published_at": published,
        "sha256": sha, "bytes": len(raw), "result": result, "counts": counts,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
