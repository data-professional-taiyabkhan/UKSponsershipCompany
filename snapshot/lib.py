"""Shared helpers for the UK sponsor register snapshot pipeline.

The register is published as a CSV with no stable URL and no official archive.
This module defines the canonical normalised form we store, so that a diff
between two days reflects real licence changes rather than whitespace churn.
"""
from __future__ import annotations

import gzip
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# The five columns the Home Office publishes. If this ever changes, we want to
# stop rather than silently write a corrupt diff.
EXPECTED_COLUMNS = ["Organisation Name", "Town/City", "County", "Type & Rating", "Route"]

ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "snapshots"
BASELINE_DIR = SNAP_DIR / "baselines"
DIFF_DIR = SNAP_DIR / "diffs"
MANIFEST = SNAP_DIR / "manifest.jsonl"

# Routes an applicant outside the sponsor's existing workforce cannot apply to.
# Kept here because it is a judgement call, not a fact from the data.
NON_EXTERNAL_ROUTES = {
    "Global Business Mobility: Senior or Specialist Worker",
    "Global Business Mobility: Graduate Trainee",
    "Global Business Mobility: UK Expansion Worker",
    "Global Business Mobility: Service Supplier",
    "Global Business Mobility: Secondment Worker",
    "Intra-company Routes",
    "Intra Company Transfers (ICT)",
}

_WS = re.compile(r"\s+")
_TRAILING_PUNCT = re.compile(r"[.,;:\-\s]+$")


def norm(value) -> str:
    """Collapse the register's very inconsistent whitespace and casing."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = _WS.sub(" ", str(value)).strip()
    s = _TRAILING_PUNCT.sub("", s)
    return s.upper()


def canonical(df: pd.DataFrame) -> pd.DataFrame:
    """Return the stored form: normalised keys plus the original display name.

    One organisation appears once per route it is licensed for, so the key is
    (name, town, route) — not the name alone.
    """
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaChanged(
            f"register is missing expected column(s) {missing}; "
            f"got {list(df.columns)}"
        )

    out = pd.DataFrame(
        {
            "name_key": df["Organisation Name"].map(norm),
            "town_key": df["Town/City"].map(norm),
            "route": df["Route"].map(lambda v: _WS.sub(" ", str(v)).strip()),
            "rating": df["Type & Rating"].map(lambda v: _WS.sub(" ", str(v)).strip()),
            # keep one readable spelling for display / joining to Companies House
            "name": df["Organisation Name"].map(lambda v: _WS.sub(" ", str(v)).strip()),
            "town": df["Town/City"].map(lambda v: _WS.sub(" ", str(v)).strip()),
            "county": df["County"].map(lambda v: _WS.sub(" ", str(v)).strip()),
        }
    )
    out["key"] = out["name_key"] + "|" + out["town_key"] + "|" + out["route"]
    # A handful of exact duplicate rows appear in the published file.
    out = out.drop_duplicates(subset="key").sort_values("key").reset_index(drop=True)
    return out


class SchemaChanged(RuntimeError):
    """Raised when the published register no longer matches EXPECTED_COLUMNS."""


@dataclass
class Diff:
    date: str
    previous_date: str
    added: pd.DataFrame
    removed: pd.DataFrame
    rating_changed: pd.DataFrame

    @property
    def is_empty(self) -> bool:
        return not (len(self.added) or len(self.removed) or len(self.rating_changed))

    def to_json(self) -> dict:
        cols = ["key", "name", "town", "county", "route", "rating"]
        return {
            "date": self.date,
            "previous_date": self.previous_date,
            "counts": {
                "added": int(len(self.added)),
                "removed": int(len(self.removed)),
                "rating_changed": int(len(self.rating_changed)),
            },
            "added": self.added[cols].to_dict("records"),
            "removed": self.removed[cols].to_dict("records"),
            "rating_changed": self.rating_changed[
                cols + ["rating_before"]
            ].to_dict("records"),
        }


def compute_diff(prev: pd.DataFrame, curr: pd.DataFrame, date: str, prev_date: str) -> Diff:
    p = prev.set_index("key")
    c = curr.set_index("key")

    added = curr[~curr["key"].isin(p.index)]
    removed = prev[~prev["key"].isin(c.index)]

    both = p.index.intersection(c.index)
    changed_keys = both[p.loc[both, "rating"].values != c.loc[both, "rating"].values]
    rating_changed = c.loc[changed_keys].reset_index()
    if len(rating_changed):
        rating_changed["rating_before"] = p.loc[changed_keys, "rating"].values
    else:
        rating_changed["rating_before"] = pd.Series(dtype=str)

    return Diff(date, prev_date, added.reset_index(drop=True),
                removed.reset_index(drop=True), rating_changed)


# ---------------------------------------------------------------- persistence

def write_baseline(df: pd.DataFrame, date: str) -> Path:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    path = BASELINE_DIR / f"{date}.csv.gz"
    df.to_csv(path, index=False, compression="gzip")
    return path


def write_diff(diff: Diff) -> Path:
    DIFF_DIR.mkdir(parents=True, exist_ok=True)
    path = DIFF_DIR / f"{diff.date}.json"
    path.write_text(json.dumps(diff.to_json(), indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def latest_baseline() -> tuple[str, pd.DataFrame] | tuple[None, None]:
    if not BASELINE_DIR.exists():
        return None, None
    files = sorted(BASELINE_DIR.glob("*.csv.gz"))
    if not files:
        return None, None
    f = files[-1]
    return f.name.replace(".csv.gz", ""), pd.read_csv(f, keep_default_na=False)


def replay_state(up_to: str | None = None) -> tuple[str, pd.DataFrame]:
    """Rebuild the register as at `up_to` from the newest baseline + its diffs.

    Storing a full snapshot every day would add ~1.5 MB to git daily. Storing a
    monthly baseline plus daily diffs keeps the repo small while remaining
    fully reproducible.
    """
    date, state = latest_baseline()
    if state is None:
        raise FileNotFoundError("no baseline yet — run fetch_register.py first")

    cols = list(state.columns)
    for path in sorted(DIFF_DIR.glob("*.json")) if DIFF_DIR.exists() else []:
        d = json.loads(path.read_text(encoding="utf-8"))
        if d["date"] <= date:
            continue
        if up_to and d["date"] > up_to:
            break
        state = state[~state["key"].isin([r["key"] for r in d["removed"]])]
        if d["added"]:
            state = pd.concat([state, pd.DataFrame(d["added"])], ignore_index=True)
        for r in d["rating_changed"]:
            state.loc[state["key"] == r["key"], "rating"] = r["rating"]
        date = d["date"]

    return date, state[cols].sort_values("key").reset_index(drop=True)


def append_manifest(entry: dict) -> None:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def last_manifest_entry() -> dict | None:
    if not MANIFEST.exists():
        return None
    lines = [l for l in MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(lines[-1]) if lines else None
