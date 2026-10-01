"""Temporary diagnostic: what can GitHub Actions reach for school-level KS4 data?"""
import json
import re

import requests

UA = {"User-Agent": "tutoring-gap-map/1.0 (+https://github.com/akshajan-r/Tutoring-Gap-Map)"}


def show(label, r):
    ctype = r.headers.get("content-type", "")
    title = re.search(r"<title>(.*?)</title>", r.text[:5000], re.S | re.I) if "html" in ctype else None
    hdrs = {k: v for k, v in r.headers.items() if k.lower() in ("server", "cf-ray", "x-azure-ref", "content-disposition", "location")}
    print(f"[{label}] {r.status_code} {r.url}\n    type={ctype} len={len(r.content)} headers={hdrs}"
          + (f"\n    title={title.group(1).strip()[:120]!r}" if title else "")
          + ("" if "html" in ctype or "json" in ctype else f"\n    first bytes={r.content[:80]!r}"))


def get(s, label, url, **kw):
    try:
        r = s.get(url, timeout=60, **kw)
        show(label, r)
        return r
    except requests.RequestException as e:
        print(f"[{label}] {type(e).__name__}: {e}")


s = requests.Session()
s.headers.update(UA)

print("=== Compare School Performance ===")
get(s, "csp landing", "https://www.compare-school-performance.service.gov.uk/download-data")
get(s, "csp download (after landing, with cookies)",
    "https://www.compare-school-performance.service.gov.uk/download-data?download=true&regions=0&filters=KS4&fileformat=csv&year=2023-2024&meta=false")

print("=== Find school and college performance data ===")
get(s, "fscpd landing", "https://www.find-school-performance-data.service.gov.uk/")
get(s, "fscpd download-data", "https://www.find-school-performance-data.service.gov.uk/download-data")

print("=== Explore Education Statistics content API ===")
for slug in ("key-stage-4-performance", "key-stage-4-performance-revised"):
    r = get(s, f"ees release {slug}",
            f"https://content.explore-education-statistics.service.gov.uk/api/publications/{slug}/releases/latest")
    if r is not None and r.ok:
        j = r.json()
        print("    keys:", list(j)[:40])
        print("    title:", j.get("title"), "| slug:", j.get("slug"), "| id:", j.get("id"))
        for key in ("downloadFiles", "dataFiles", "dataSets", "files"):
            for f in j.get(key) or []:
                print(f"    {key}: " + json.dumps({k: f.get(k) for k in ("id", "name", "fileName", "size", "type", "subjectId") if k in f}))

print("=== Explore Education Statistics public API ===")
r = get(s, "ees api publications", "https://api.education.gov.uk/statistics/v1/publications?search=key%20stage%204&pageSize=20")
if r is not None and r.ok:
    for p in r.json().get("results", []):
        print(f"    pub {p.get('id')} {p.get('title')!r}")
        d = get(s, "  data-sets", f"https://api.education.gov.uk/statistics/v1/publications/{p['id']}/data-sets?pageSize=50")
        if d is not None and d.ok:
            for ds in d.json().get("results", []):
                print(f"      ds {ds.get('id')} {ds.get('title')!r}")
