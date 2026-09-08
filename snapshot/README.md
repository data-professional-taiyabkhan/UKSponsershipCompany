# Sponsor register snapshots

The Home Office republishes the [Register of licensed sponsors: workers](https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers)
on most working days. **There is no official archive of it** — not on data.gov.uk,
not anywhere else. The asset URL contains an opaque hash that changes on every
publish, and the filename convention has already changed once.

So the only way to have a history is to keep one. That is what this does.

## Running it

```bash
pip install pandas
python snapshot/fetch_register.py     # daily; safe to run repeatedly
python snapshot/report.py --days 7    # what changed this week
```

`fetch_register.py` resolves the current CSV through the gov.uk Content API
(never a hardcoded asset URL), hashes it, and exits early if the file is
byte-identical to the last run.

## Storage design

A full snapshot is ~4.3 MB gzipped (organisation names are near-unique, so they
compress poorly). Committing one every day would add ~1.5 GB to the repo in a
year. Instead:

```
snapshots/
  baselines/YYYY-MM-DD.csv.gz   full state, written on the 1st of each month
  diffs/YYYY-MM-DD.json         that day's added / removed / rating changes
  manifest.jsonl                one line per fetch: source URL, sha256, outcome
```

Any past day is reconstructed by `lib.replay_state()` — newest baseline, then
replay the diffs. ~50 MB a year against ~1.5 GB, fully reproducible, and every
row traceable to the exact file it came from via the manifest.

Measured on the first real diff: 4 Sep -> 8 Sep 2026 was 146 licences added,
92 removed, 3 rating changes — a 56 KB JSON file against a 4.3 MB snapshot.

## Keys and normalisation

The published file is dirty: leading and trailing whitespace in names and
towns, inconsistent casing, an often-empty County. An organisation appears
**once per route it holds**, so the identity key is
`normalised(name) | normalised(town) | route` — not the name alone.

## Reading the diffs honestly

**A sponsor disappearing from the register is not a revocation.** It can be a
voluntary surrender, an expiry, a merger, or a rename. The Home Office does not
publish a revocations list for the worker routes; only aggregate counts of
"action taken against sponsors" in the quarterly
[sponsorship transparency data](https://www.gov.uk/government/statistical-data-sets/migration-transparency-data).
Label these rows **"removed from register"** and nothing stronger. Asserting a
revocation from a diff would be defamatory if wrong.

Newly added licences carry no such ambiguity and are the useful signal.

## Licence

Register data is © Crown copyright, published under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
