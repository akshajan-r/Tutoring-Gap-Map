"""Best-effort download of the raw files into data/raw/.

Government download endpoints move around (Compare School Performance is being
replaced by "Find school and college performance data", GIAS file names carry
the date, IoD URLs contain an asset hash). So every step falls back to printing
where to get the file by hand and where to put it.
"""
from __future__ import annotations

import datetime as dt
import io
import zipfile
from pathlib import Path

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


def download_ks4(raw_dir: Path, years: list[str]) -> list[str]:
    src = SOURCES["ks4"]
    missing = []
    for year in years:
        dest = raw_dir / "ks4" / year
        if list(dest.glob("england_ks4*.csv")):
            print(f"  ks4 {year}: already present")
            continue
        print(f"  ks4 {year}: downloading")
        r = _get(src["url"].format(year=year), timeout=300)
        if r is None:
            _manual(f"KS4 results for {year}", src["landing"], dest / "england_ks4final.csv",
                    "Choose: All of England > Key stage 4 results > CSV, then unzip.")
            missing.append(f"ks4 {year}")
            continue
        dest.mkdir(parents=True, exist_ok=True)
        if r.content[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                names = [n for n in z.namelist() if Path(n).name.lower().startswith("england_ks4")]
                for n in names:
                    (dest / Path(n).name).write_bytes(z.read(n))
                print(f"    saved {', '.join(Path(n).name for n in names) or 'nothing (no england_ks4*.csv in zip)'}")
            if not names:
                missing.append(f"ks4 {year}")
        elif r.content.lstrip()[:1] == b"<":
            print("    got a web page, not a CSV (the download form has probably changed)")
            _manual(f"KS4 results for {year}", src["landing"], dest / "england_ks4final.csv")
            missing.append(f"ks4 {year}")
        else:
            (dest / "england_ks4final.csv").write_bytes(r.content)
            print("    saved england_ks4final.csv")
    return missing


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


def download_all(raw_dir: Path, years: list[str]) -> list[str]:
    """Returns the sources that still need fetching by hand (empty = all done)."""
    print(f"Downloading into {raw_dir}")
    missing = download_ks4(raw_dir, years) + download_gias(raw_dir) + download_imd(raw_dir)
    print("Optional: put an ONS Postcode Directory CSV in data/raw/onspd/ to fill missing LSOAs.")
    if missing:
        print(f"Still missing: {', '.join(missing)}")
    return missing
