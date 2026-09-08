"""Build the compact geo lookup the site joins against at deploy time.

The register carries no coordinates and no postcode — only organisation name
and town. cleaned_geocoded_data.csv is the reusable asset: ~110k sponsors
matched to their Companies House registered address and geocoded. This turns it
into two small gzipped tables the Node build can join cheaply:

  orgs.tsv.gz   name_key \t town_key \t lat \t lng \t postcode

NOTE ON WHAT THE COORDINATES MEAN: the source file geocoded
"<organisation name>, <town>, United Kingdom" — NOT the registered address. So a
point is the geocoder's best guess at the organisation, and the postcode beside
it is the Companies House registered office, which is separate data and can
disagree (a firm registered in RG1 may be plotted in the town the register
lists). Never describe these as address-level coordinates.
  towns.tsv.gz  town_key \t lat \t lng \t n        (median centroid)

Coordinates are stored to 5dp — about a metre, far beyond what a registered
office address justifies.

    python build_geo_lookup.py cleaned_geocoded_data.csv site/geodata
"""
from __future__ import annotations

import gzip
import re
import sys
from pathlib import Path

import pandas as pd

WS = re.compile(r"\s+")
TRAIL = re.compile(r"[.,;:\-\s]+$")
POSTCODE = re.compile(r"([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})")


def norm(s) -> str:
    return TRAIL.sub("", WS.sub(" ", str(s)).strip().upper())


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    src, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    g = pd.read_csv(src, keep_default_na=False, dtype=str)
    g["lat"] = pd.to_numeric(g["latitude"], errors="coerce")
    g["lng"] = pd.to_numeric(g["longitude"], errors="coerce")
    g = g.dropna(subset=["lat", "lng"])
    # A handful of rows geocode outside the UK bounding box — drop them rather
    # than drawing a sponsor in the Atlantic.
    g = g[g["lat"].between(49.8, 61.0) & g["lng"].between(-8.7, 2.1)]

    g["nk"] = g["Organisation Name"].map(norm)
    g["tk"] = g["Town/City"].map(norm)
    # Take the LAST postcode-shaped match: UK addresses put the postcode at the
    # end, and fragments like "SUITE E2, 2ND FLOOR" match the pattern earlier in
    # the string.
    g["pc"] = g["Full Address"].str.upper().map(
        lambda s: (POSTCODE.findall(s)[-1] if isinstance(s, str) and POSTCODE.findall(s) else None)
    )
    g["pc"] = g["pc"].fillna("").str.replace(r"\s+", " ", regex=True)

    orgs = g.drop_duplicates(subset=["nk", "tk"])[["nk", "tk", "lat", "lng", "pc"]]
    lines = [
        f"{r.nk}\t{r.tk}\t{r.lat:.5f}\t{r.lng:.5f}\t{r.pc}"
        for r in orgs.itertuples()
    ]
    p = outdir / "orgs.tsv.gz"
    with gzip.open(p, "wt", encoding="utf-8", compresslevel=9) as fh:
        fh.write("\n".join(lines))
    print(f"orgs.tsv.gz   {len(lines):,} rows  {p.stat().st_size/1e6:.2f} MB")

    # Town centroids: median is used because a few registered offices sit well
    # outside the town they name, and a mean would drag the pin with them.
    tc = g.groupby("tk").agg(lat=("lat", "median"), lng=("lng", "median"), n=("lat", "size"))
    tc = tc[tc["n"] >= 2]
    tlines = [f"{k}\t{r.lat:.5f}\t{r.lng:.5f}\t{int(r.n)}" for k, r in tc.iterrows()]
    p2 = outdir / "towns.tsv.gz"
    with gzip.open(p2, "wt", encoding="utf-8", compresslevel=9) as fh:
        fh.write("\n".join(tlines))
    print(f"towns.tsv.gz  {len(tlines):,} towns  {p2.stat().st_size/1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
