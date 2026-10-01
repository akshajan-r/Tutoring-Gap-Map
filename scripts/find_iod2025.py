"""List the English Indices of Deprivation files on GOV.UK (temporary helper)."""
import requests

for slug in ("english-indices-of-deprivation-2025", "english-indices-of-deprivation-2019"):
    r = requests.get(f"https://www.gov.uk/api/content/government/statistics/{slug}", timeout=60)
    print(slug, r.status_code)
    if r.ok:
        for a in r.json().get("details", {}).get("attachments", []):
            print(f"  {a.get('title')!r}\n    {a.get('url')}")
