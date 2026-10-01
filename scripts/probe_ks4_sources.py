"""Temporary diagnostic (round 2): does Explore Education Statistics have school-level KS4 files?"""
import json

import requests

UA = {"User-Agent": "tutoring-gap-map/1.0 (+https://github.com/akshajan-r/Tutoring-Gap-Map)"}
PUB = "c8756008-ed50-4632-9b96-01b5ca002a43"   # 'Key stage 4 performance' (found in round 1)
API = "https://api.education.gov.uk/statistics/v1"
CONTENT = "https://content.explore-education-statistics.service.gov.uk/api"
s = requests.Session()
s.headers.update(UA)


def get(label, url, show_body=400):
    try:
        r = s.get(url, timeout=60)
    except requests.RequestException as e:
        print(f"[{label}] {type(e).__name__}: {e}")
        return None
    print(f"[{label}] {r.status_code} {url}  type={r.headers.get('content-type')} len={len(r.content)}")
    if not r.ok:
        print("    body:", r.text[:show_body].replace("\n", " "))
    return r


def dump(obj, depth=0, maxlist=60):
    """Print names/titles/ids found anywhere in a JSON object."""
    if isinstance(obj, dict):
        bits = {k: obj[k] for k in ("id", "title", "name", "fileName", "slug", "summary", "size", "releaseId", "timePeriods", "latestReleaseId")
                if k in obj and not isinstance(obj[k], (dict, list))}
        if bits:
            print("    " * depth + json.dumps(bits)[:300])
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                if isinstance(v, list) and v and not isinstance(v[0], (dict, list)):
                    continue
                print("    " * depth + f"  .{k}:")
                dump(v, depth + 1, maxlist)
    elif isinstance(obj, list):
        for x in obj[:maxlist]:
            dump(x, depth, maxlist)


print("=== Public API: data sets for KS4 performance ===")
for q in ("?page=1&pageSize=20", "", "?pageSize=20"):
    r = get("api data-sets", f"{API}/publications/{PUB}/data-sets{q}")
    if r is not None and r.ok:
        dump(r.json())
        break

print("=== Content API: publication + releases ===")
for path in (f"publications/key-stage-4-performance/title", f"publications/key-stage-4-performance/releases",
             f"publications/key-stage-4-performance/releases/latest", f"publication/key-stage-4-performance/releases/latest"):
    r = get("content", f"{CONTENT}/{path}")
    if r is not None and r.ok:
        dump(r.json(), maxlist=15)

print("=== Content API: data catalogue for the publication ===")
for path in (f"data-sets?publicationId={PUB}&latestOnly=true&pageSize=100",
             f"data-sets?publicationId={PUB}&latestOnly=false&pageSize=100",
             f"data-set-files?publicationId={PUB}&latestOnly=false&pageSize=100",
             f"data-set-files?searchTerm=school%20level%20key%20stage%204&pageSize=50"):
    r = get("catalogue", f"{CONTENT}/{path}")
    if r is not None and r.ok:
        dump(r.json(), maxlist=100)
