/**
 * Build the static data the site loads.
 *
 * The register is fetched at build time rather than committed, so the repo
 * stays free of a 5 MB dataset that would change every day. The gov.uk Content
 * API is asked where today's CSV lives — the asset URL contains an opaque hash
 * that changes on every publish, so it can never be hardcoded.
 */
import { mkdir, writeFile, readFile, readdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";

const OUT = path.join(process.cwd(), "public", "data");
const CONTENT_API =
  "https://www.gov.uk/api/content/government/publications/register-of-licensed-sponsors-workers";

// Routes that only move an employer's existing overseas staff into the UK, or
// are otherwise closed to an ordinary external applicant.
const NON_EXTERNAL = new Set([
  "Global Business Mobility: Senior or Specialist Worker",
  "Global Business Mobility: Graduate Trainee",
  "Global Business Mobility: UK Expansion Worker",
  "Global Business Mobility: Service Supplier",
  "Global Business Mobility: Secondment Worker",
  "Intra-company Routes",
  "Intra Company Transfers (ICT)",
]);

const UA = "uk-sponsor-map-build/1.0 (+https://github.com/data-professional-taiyabkhan/UKSponsershipCompany)";

async function getJSON(url) {
  const r = await fetch(url, { headers: { "user-agent": UA } });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} for ${url}`);
  return r.json();
}

async function resolveCsvUrl() {
  const doc = await getJSON(CONTENT_API);
  const atts = doc?.details?.attachments ?? [];
  const hit = atts.find((a) => {
    const s = `${a.title ?? ""} ${a.url ?? ""}`.toLowerCase();
    return a.url?.toLowerCase().endsWith(".csv") &&
      s.includes("worker") && !s.includes("student");
  });
  if (!hit) throw new Error("no worker-register CSV on the Content API response");
  return { url: hit.url, published: doc.public_updated_at ?? null };
}

/** Minimal RFC4180 parser — the register contains quoted commas in names. */
function parseCSV(text) {
  const rows = [];
  let row = [], field = "", inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; } else inQ = false;
      } else field += c;
    } else if (c === '"') inQ = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return rows;
}

const tidy = (s) => (s ?? "").replace(/\s+/g, " ").trim();

async function buildRegister() {
  const { url, published } = await resolveCsvUrl();
  console.log(`fetching ${url}`);
  const res = await fetch(url, { headers: { "user-agent": UA } });
  if (!res.ok) throw new Error(`${res.status} fetching register CSV`);
  const text = await res.text();

  const rows = parseCSV(text);
  const header = rows[0].map(tidy);
  const expected = ["Organisation Name", "Town/City", "County", "Type & Rating", "Route"];
  if (expected.some((c, i) => header[i] !== c)) {
    throw new Error(`register schema changed. expected ${expected} got ${header}`);
  }

  // One org holds one row per route. Group so the site shows an employer once
  // with all its routes, which is how a person actually thinks about it.
  const orgs = new Map();
  const routeIdx = new Map(), ratingIdx = new Map();
  const idOf = (m, v) => { if (!m.has(v)) m.set(v, m.size); return m.get(v); };

  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    if (!r || r.length < 5) continue;
    const name = tidy(r[0]), town = tidy(r[1]), county = tidy(r[2]);
    const rating = tidy(r[3]), route = tidy(r[4]);
    if (!name) continue;
    const key = `${name.toUpperCase()}|${town.toUpperCase()}`;
    let o = orgs.get(key);
    if (!o) { o = { name, town, county, ratings: new Set(), routes: new Set() }; orgs.set(key, o); }
    o.routes.add(idOf(routeIdx, route));
    o.ratings.add(idOf(ratingIdx, rating));
    if (!o.county && county) o.county = county;
  }

  const routes = [...routeIdx.keys()], ratings = [...ratingIdx.keys()];

  // Tab-separated blob: far smaller than an array of objects, and parsing
  // 127k lines with split() is a few milliseconds in the browser.
  const lines = [];
  for (const o of orgs.values()) {
    lines.push([
      o.name, o.town, o.county,
      [...o.ratings].join(","), [...o.routes].join(","),
    ].join("\t"));
  }
  lines.sort((a, b) => a.localeCompare(b));

  const payload = {
    generated: new Date().toISOString(),
    source_url: url,
    gov_published_at: published,
    routes, ratings,
    non_external: routes.map((r) => (NON_EXTERNAL.has(r) ? 1 : 0)),
    licence_rows: rows.length - 1,
    org_count: orgs.size,
    rows: lines.join("\n"),
  };
  await writeFile(path.join(OUT, "sponsors.json"), JSON.stringify(payload));
  console.log(`sponsors.json — ${orgs.size.toLocaleString()} orgs, ` +
              `${(rows.length - 1).toLocaleString()} licence rows, ` +
              `${(JSON.stringify(payload).length / 1e6).toFixed(1)} MB raw`);
  return { routes, ratings, orgCount: orgs.size, licenceRows: rows.length - 1, published };
}

const RAW = "https://raw.githubusercontent.com/data-professional-taiyabkhan/UKSponsershipCompany/main";
const API = "https://api.github.com/repos/data-professional-taiyabkhan/UKSponsershipCompany/contents/snapshots/diffs";

/** Locate the daily diffs, whether or not the build is scoped to site/. */
async function listDiffs() {
  for (const dir of [
    path.join(process.cwd(), "..", "snapshots", "diffs"),
    path.join(process.cwd(), "snapshots", "diffs"),
  ]) {
    if (existsSync(dir)) {
      const files = (await readdir(dir)).filter((f) => f.endsWith(".json")).sort();
      return { kind: "fs", dir, files };
    }
  }
  // Vercel may scope the checkout to the root directory, so fall back to the
  // repository contents API rather than silently shipping an empty feed.
  try {
    const r = await fetch(API, { headers: { "user-agent": UA, accept: "application/vnd.github+json" } });
    if (!r.ok) throw new Error(`${r.status}`);
    const files = (await r.json())
      .filter((e) => e.type === "file" && e.name.endsWith(".json"))
      .map((e) => e.name).sort();
    console.log(`diffs via GitHub API (${files.length} files)`);
    return { kind: "http", files };
  } catch (e) {
    console.log(`no diffs available (${e.message}) — shipping an empty feed`);
    return { kind: "none", files: [] };
  }
}

/** Roll up the daily diffs into a "recently licensed" feed. */
async function buildChanges() {
  const src = await listDiffs();
  if (!src.files.length) {
    await writeFile(path.join(OUT, "changes.json"),
      JSON.stringify({ days: [], added: [], removed: [], rating_changed: [] }));
    return;
  }
  const added = [], removed = [], ratingChanged = [], days = [];
  for (const f of src.files.slice(-60)) {
    const text = src.kind === "fs"
      ? await readFile(path.join(src.dir, f), "utf8")
      : await fetch(`${RAW}/snapshots/diffs/${f}`, { headers: { "user-agent": UA } }).then((r) => r.text());
    const d = JSON.parse(text);
    days.push({ date: d.date, ...d.counts });
    for (const r of d.added) added.push({ ...r, date: d.date });
    for (const r of d.removed) removed.push({ ...r, date: d.date });
    for (const r of d.rating_changed) ratingChanged.push({ ...r, date: d.date });
  }
  await writeFile(path.join(OUT, "changes.json"),
    JSON.stringify({ days, added, removed, rating_changed: ratingChanged }));
  console.log(`changes.json — ${days.length} days, ${added.length} added, ` +
              `${removed.length} removed, ${ratingChanged.length} rating changes`);
}

await mkdir(OUT, { recursive: true });
const reg = await buildRegister();
await buildChanges();
await writeFile(path.join(OUT, "meta.json"), JSON.stringify({
  built: new Date().toISOString(),
  org_count: reg.orgCount,
  licence_rows: reg.licenceRows,
  gov_published_at: reg.published,
}));
console.log("build complete");
