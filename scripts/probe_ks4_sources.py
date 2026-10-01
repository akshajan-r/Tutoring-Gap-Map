"""Temporary diagnostic (round 3): shape of EES 'Performance tables schools data'."""
import csv
import io
import json
from collections import Counter, defaultdict

import requests

UA = {"User-Agent": "tutoring-gap-map/1.0 (+https://github.com/akshajan-r/Tutoring-Gap-Map)"}
API = "https://api.education.gov.uk/statistics/v1"
CONTENT = "https://content.explore-education-statistics.service.gov.uk/api"
DS = "19e39901-a96c-be76-b9c2-6af54ae076d2"   # Performance tables schools data
PUB = "c8756008-ed50-4632-9b96-01b5ca002a43"
s = requests.Session()
s.headers.update(UA)


def get(label, url, **kw):
    r = s.get(url, timeout=120, **kw)
    print(f"[{label}] {r.status_code} {url} len={r.headers.get('content-length') or len(r.content)}")
    if not r.ok:
        print("    body:", r.text[:300].replace("\n", " "))
    return r


print("=== data set summary ===")
r = get("ds", f"{API}/data-sets/{DS}")
if r.ok:
    j = r.json()
    print(json.dumps({k: v for k, v in j.items() if k != "latestVersion"})[:600])
    print(json.dumps(j.get("latestVersion"))[:1500])

print("=== data set meta ===")
r = get("meta", f"{API}/data-sets/{DS}/meta")
if r.ok:
    m = r.json()
    print("keys:", list(m))
    print("timePeriods:", json.dumps(m.get("timePeriods"))[:600])
    print("geographicLevels:", json.dumps(m.get("geographicLevels"))[:400])
    for f in m.get("filters", []):
        opts = f.get("options", [])
        print(f"filter {f.get('id')} {f.get('label')!r} column={f.get('column')} n={len(opts)}: "
              + ", ".join(repr(o.get('label')) for o in opts[:25]))
    inds = m.get("indicators", [])
    print(f"indicators ({len(inds)}):")
    for i in inds:
        print(f"  {i.get('id')} column={i.get('column')} unit={i.get('unit')!r} label={i.get('label')!r}")

print("=== CSV download (public API) ===")
try:
    r = s.get(f"{API}/data-sets/{DS}/csv", timeout=600, stream=True)
    print("status", r.status_code, "type", r.headers.get("content-type"), "len", r.headers.get("content-length"))
    if r.ok:
        raw = r.content
        if raw[:2] == b"PK":
            import zipfile
            z = zipfile.ZipFile(io.BytesIO(raw))
            print("zip members:", z.namelist())
            raw = z.read(z.namelist()[0])
        text = raw.decode("utf-8-sig")
        print("bytes:", len(raw))
        rows = list(csv.DictReader(io.StringIO(text)))
        print("rows:", len(rows))
        cols = list(rows[0])
        print("columns:", cols)
        for c in cols:
            vals = Counter(r[c] for r in rows)
            if len(vals) <= 40:
                print(f"  {c}: {dict(vals.most_common(40))}")
            else:
                print(f"  {c}: {len(vals)} distinct, e.g. {[v for v, _ in vals.most_common(6)]}")
        urn_col = next((c for c in cols if "urn" in c.lower()), None)
        if urn_col:
            by = defaultdict(list)
            for r in rows:
                by[r[urn_col]].append(r)
            u = next(k for k, v in by.items() if len(v) > 1 and k)
            print(f"all rows for one school ({urn_col}={u}):")
            for r in by[u][:30]:
                print("   ", json.dumps(r)[:900])
except Exception as e:
    print("csv error:", type(e).__name__, e)

print("=== Content API data catalogue: files across releases ===")
for page in (1, 2):
    r = get("files", f"{CONTENT}/data-set-files?publicationId={PUB}&latestOnly=false&pageSize=40&page={page}")
    if r.ok:
        j = r.json()
        for f in j.get("results", []):
            print("  " + json.dumps({k: f.get(k) for k in ("id", "fileId", "title", "release", "releaseId", "timePeriods", "file") if k in f})[:500])
        if page >= (j.get("paging") or {}).get("totalPages", 1):
            break
