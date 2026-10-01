"""Best-effort download of the raw files into data/raw/.

GIAS file names carry the date and IoD URLs contain an asset hash, so every step
falls back to printing where to get the file by hand and where to put it.
"""
from __future__ import annotations

import datetime as dt
import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

from .config import SOURCES

HEADERS = {"User-Agent": "tutoring-gap-map/1.0 (+https://github.com/akshajan-r/tutoring-gap-map)"}


def _get(url: str, timeout: int = 120) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200 and r.content:
            return r
        print(f"    HTTP {r.status_code} for {url}")
    except requests.RequestException as e:
        print(f"    {type(e).__name__} fetching {url.split('?')[0]}")
    return None


def _manual(what: str, landing: str, dest: Path, note: str = "") -> None:
    print(f"  ! Couldn't download {what} automatically.\n"
          f"    Get it from {landing}\n"
          f"    and save it under {dest}{(chr(10) + '    ' + note) if note else ''}")


def download_ks4(raw_dir: Path) -> list[str]:
    """School-level KS4 results from the Explore Education Statistics API.

    The full file is ~100 MB; only the overall and disadvantage-status rows and
    the columns the pipeline reads are kept (a few MB).
    """
    from .clean import slim_ees_ks4

    src = SOURCES["ks4"]
    dest = raw_dir / "ks4" / "ees_ks4_schools.csv"
    print("  ks4: downloading from Explore Education Statistics")
    r = _get(src["url"], timeout=600)
    if r is None or r.content.lstrip()[:1] == b"<":
        _manual("KS4 results", src["landing"], dest,
                "Download 'Key stage 4 institution level - Schools (performance)' as CSV.")
        return ["ks4"]
    content = r.content
    if content[:2] == b"PK":  # zipped
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            content = z.read(next(n for n in z.namelist() if n.lower().endswith(".csv")))
    raw = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, low_memory=False)
    slim = slim_ees_ks4(raw)
    dest.parent.mkdir(parents=True, exist_ok=True)
    slim.to_csv(dest, index=False)
    years = sorted(slim["time_period"].unique())
    print(f"    saved {dest.name}: {slim['school_urn'].nunique():,} schools, years {', '.join(years)}")
    print(f"    (older years: add england_ks4final.csv by hand from {src['older_years_landing']})")
    return []


def download_gias(raw_dir: Path) -> list[str]:
    src = SOURCES["gias"]
    dest = raw_dir / "gias"
    dest.mkdir(parents=True, exist_ok=True)
    # Files are published daily with the date in the name; walk back a few days.
    for back in range(0, 8):
        date = (dt.date.today() - dt.timedelta(days=back)).strftime("%Y%m%d")
        r = _get(src["url"].format(date=date), timeout=300)
        if r is None:
            continue
        (dest / f"edubasealldata{date}.csv").write_bytes(r.content)
        print(f"  gias: saved edubasealldata{date}.csv")
        links = _get(src["links_url"].format(date=date))
        if links is not None:
            (dest / f"links_edubasealldata{date}.csv").write_bytes(links.content)
            print(f"  gias: saved links_edubasealldata{date}.csv")
        return []
    _manual("Get Information About Schools", src["landing"], dest,
            "Download 'All establishment data' and 'All links data' (CSV).")
    return ["gias"]


def download_imd(raw_dir: Path) -> list[str]:
    src = SOURCES["imd"]
    dest = raw_dir / "imd"
    if dest.exists() and any(dest.iterdir()):
        print("  imd: already present")
        return []
    r = _get(src["url"], timeout=300)
    if r is None:
        _manual("the English Indices of Deprivation", src["landing"], dest,
                "Use the LSOA-level file with scores (IoD2019 'File 7', or the IoD2025 equivalent).")
        return ["imd"]
    dest.mkdir(parents=True, exist_ok=True)
    name = src["url"].rsplit("/", 1)[-1]
    (dest / name).write_bytes(r.content)
    print(f"  imd: saved {name}")
    return []


def download_all(raw_dir: Path) -> list[str]:
    """Returns the sources that still need fetching by hand (empty = all done)."""
    print(f"Downloading into {raw_dir}")
    missing = download_ks4(raw_dir) + download_gias(raw_dir) + download_imd(raw_dir)
    print("Optional: put an ONS Postcode Directory CSV in data/raw/onspd/ to fill missing LSOAs.")
    if missing:
        print(f"Still missing: {', '.join(missing)}")
    return missing
