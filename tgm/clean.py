"""Readers that turn each raw government file into a tidy pandas DataFrame.

Every reader looks columns up by name (with fallbacks) rather than position,
because DfE, GIAS and MHCLG all rename or reorder columns between releases.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .geo import bng_to_wgs84

# Codes DfE uses in place of numbers: suppressed, not applicable, no entries,
# low coverage, not published, and the newer one-letter EES symbols.
SUPPRESSION_CODES = {
    "SUPP", "NE", "NA", "NP", "LOWCOV", "NEW", "SP", "DNS", "NAT", "NEWSCH",
    "x", "c", "z", "u", "low", ":", ".", "-", "",
}


def read_csv_any_encoding(path: Path, **kwargs) -> pd.DataFrame:
    """GIAS ships cp1252; DfE and ONS ship UTF-8 (sometimes with a BOM)."""
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc, keep_default_na=False,
                               low_memory=False, **kwargs)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, dtype=str, encoding="latin-1", keep_default_na=False,
                       low_memory=False, **kwargs)


def to_number(series: pd.Series) -> pd.Series:
    """'23%' -> 23.0, '1,204' -> 1204.0, 'SUPP' -> NaN."""
    s = series.astype(str).str.strip()
    s = s.mask(s.isin(SUPPRESSION_CODES))
    s = s.str.replace("%", "", regex=False).str.replace(",", "", regex=False)
    return pd.to_numeric(s, errors="coerce")


def normalise_postcode(series: pd.Series) -> pd.Series:
    """'sw1a1aa' / 'SW1A  1AA' -> 'SW1A 1AA'. Blank -> NaN."""
    s = series.fillna("").astype(str).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    s = s.where(s.str.len().between(5, 7))
    return s.str[:-3] + " " + s.str[-3:]


def _pick(df: pd.DataFrame, *candidates: str) -> str | None:
    """First candidate column present (case-insensitive exact match)."""
    lookup = {c.upper(): c for c in df.columns}
    for cand in candidates:
        if cand.upper() in lookup:
            return lookup[cand.upper()]
    return None


def _pick_regex(df: pd.DataFrame, pattern: str) -> str | None:
    rx = re.compile(pattern, re.IGNORECASE)
    for col in df.columns:
        if rx.search(col):
            return col
    return None


# ---------------------------------------------------------------------------
# KS4 school performance tables (england_ks4final.csv)
# ---------------------------------------------------------------------------

# tidy name -> candidate DfE column names (first match wins)
KS4_FIELDS = {
    "total_pupils": ["TPUP"],
    "n_disadv": ["TFSM6CLA1A"],
    "n_nondisadv": ["TNOTFSM6CLA1A"],
    "pct_disadv": ["PTFSM6CLA1A"],
    "att8_all": ["ATT8SCR"],
    "att8_disadv": ["ATT8SCR_FSM6CLA1A"],
    "att8_nondisadv": ["ATT8SCR_NFSM6CLA1A"],
    "p8_all": ["P8MEA"],
    "p8_disadv": ["P8MEA_FSM6CLA1A"],
    "p8_nondisadv": ["P8MEA_NFSM6CLA1A"],
    "basics94_all": ["PTL2BASICS_94"],
    "basics94_disadv": ["PTFSM6CLA1ABASICS_94"],
    "basics94_nondisadv": ["PTNOTFSM6CLA1ABASICS_94"],
}


def academic_year_label(year: str) -> tuple[str, int]:
    """'2022-2023' -> ('2022-23', 2022)."""
    m = re.match(r"(\d{4})\D*(\d{2,4})?", str(year))
    if not m:
        raise ValueError(f"Can't parse academic year from {year!r}")
    start = int(m.group(1))
    return f"{start}-{str(start + 1)[-2:]}", start


def read_ks4(path: Path, year: str) -> pd.DataFrame:
    raw = read_csv_any_encoding(path)
    rectype_col = _pick(raw, "RECTYPE")
    urn_col = _pick(raw, "URN")
    if urn_col is None:
        raise ValueError(f"{path}: no URN column - is this a KS4 school-level file?")

    df = raw
    if rectype_col:
        # 1 = mainstream school, 2 = special school; 4/5/7 are LA and national totals.
        df = df[df[rectype_col].str.strip().isin(["1", "2"])]
    df = df.assign(urn=pd.to_numeric(df[urn_col], errors="coerce")).dropna(subset=["urn"])

    label, start = academic_year_label(year)
    out = pd.DataFrame({
        "academic_year": label,
        "year_start": start,
        "urn": df["urn"].astype("int64"),
        "ks4_school_name": df[_pick(df, "SCHNAME")] if _pick(df, "SCHNAME") else None,
        "ks4_postcode": normalise_postcode(df[_pick(df, "PCODE")]) if _pick(df, "PCODE") else None,
        "is_special": (df[rectype_col].str.strip() == "2").astype(int) if rectype_col else 0,
    })
    for field, candidates in KS4_FIELDS.items():
        col = _pick(df, *candidates)
        out[field] = to_number(df[col]).values if col else np.nan

    # Pupil counts aren't in every year's file: derive them from the percentages.
    derived = (out["total_pupils"] * out["pct_disadv"] / 100).round()
    out["n_disadv"] = out["n_disadv"].fillna(derived)
    out["n_nondisadv"] = out["n_nondisadv"].fillna(out["total_pupils"] - out["n_disadv"])
    out["pct_disadv"] = out["pct_disadv"].fillna(100 * out["n_disadv"] / out["total_pupils"])
    for c in ("total_pupils", "n_disadv", "n_nondisadv"):
        out[c] = out[c].astype("Int64")

    # A handful of schools appear twice (e.g. a mid-year re-registration): keep the larger cohort.
    out = out.sort_values("total_pupils", ascending=False).drop_duplicates("urn")
    return out.reset_index(drop=True)


# Identifier columns read_ks4 uses alongside KS4_FIELDS.
KS4_ID_COLUMNS = ["RECTYPE", "LEA", "URN", "SCHNAME", "PCODE"]


def slim_ks4(path: Path) -> tuple[int, int]:
    """Rewrite a KS4 file in place with only the columns this project reads.

    The full file has several hundred columns. Slimmed copies are small enough to
    commit, so the GitHub Pages workflow can use them without downloading.
    Returns (bytes before, bytes after).
    """
    before = path.stat().st_size
    raw = read_csv_any_encoding(path)
    wanted = KS4_ID_COLUMNS + [c for cands in KS4_FIELDS.values() for c in cands]
    keep = [c for c in raw.columns if c.upper() in {w.upper() for w in wanted}]
    if not any(c.upper() == "URN" for c in keep):
        raise ValueError(f"{path}: no URN column - is this the school-level KS4 file?")
    raw[keep].to_csv(path, index=False, encoding="utf-8")
    return before, path.stat().st_size


def find_ks4_files(ks4_dir: Path) -> dict[str, Path]:
    """{'2022-2023': path} for each year folder that has a KS4 school file.

    Prefers final > revised > provisional when several are present.
    """
    found: dict[str, Path] = {}
    if not ks4_dir.exists():
        return found
    preference = ["final", "revised", "provisional"]
    for year_dir in sorted(p for p in ks4_dir.iterdir() if p.is_dir()):
        files = sorted(year_dir.glob("england_ks4*.csv"))
        files = [f for f in files if "meta" not in f.name.lower()]
        if not files:
            continue
        files.sort(key=lambda f: next((i for i, k in enumerate(preference) if k in f.name.lower()), 9))
        found[year_dir.name] = files[0]
    return found


# ---------------------------------------------------------------------------
# Get Information About Schools (edubasealldata + links)
# ---------------------------------------------------------------------------

GIAS_FIELDS = {
    "urn": ["URN"],
    "school_name": ["EstablishmentName"],
    "postcode": ["Postcode"],
    "la_code": ["LA (code)"],
    "la_name": ["LA (name)"],
    "region": ["GOR (name)"],
    "establishment_type": ["TypeOfEstablishment (name)"],
    "type_group": ["EstablishmentTypeGroup (name)"],
    "phase": ["PhaseOfEducation (name)"],
    "gender": ["Gender (name)"],
    "religious_character": ["ReligiousCharacter (name)"],
    "admissions_policy": ["AdmissionsPolicy (name)"],
    "urban_rural": ["UrbanRural (name)"],
    "status": ["EstablishmentStatus (name)"],
    "open_date": ["OpenDate"],
    "close_date": ["CloseDate"],
    "lsoa_code": ["LSOA (code)"],
    "district_code": ["DistrictAdministrative (code)"],
    "district_name": ["DistrictAdministrative (name)"],
    "trust_name": ["Trusts (name)"],
    "easting": ["Easting"],
    "northing": ["Northing"],
}


def school_type_category(establishment_type: str, type_group: str) -> str:
    """Collapse ~40 GIAS establishment types into the handful a dashboard filter needs."""
    t = (establishment_type or "").lower()
    g = (type_group or "").lower()
    if "special" in t or g == "special schools":
        return "Special"
    if g.startswith("independent"):
        return "Independent"
    if "academy converter" in t:
        return "Academy (converter)"
    if "sponsor led" in t:
        return "Academy (sponsor led)"
    if g == "free schools" or "free school" in t or "university technical" in t or "studio" in t:
        return "Free school / UTC / studio"
    if g.startswith("local authority maintained"):
        return "LA maintained"
    return "Other"


def read_gias(path: Path) -> pd.DataFrame:
    raw = read_csv_any_encoding(path)
    out = pd.DataFrame(index=raw.index)
    for field, candidates in GIAS_FIELDS.items():
        col = _pick(raw, *candidates)
        out[field] = raw[col] if col else None

    out["urn"] = pd.to_numeric(out["urn"], errors="coerce")
    out = out.dropna(subset=["urn"])
    out["urn"] = out["urn"].astype("int64")
    out["postcode"] = normalise_postcode(out["postcode"])
    for c in ("open_date", "close_date"):
        out[c] = pd.to_datetime(out[c].where(out[c] != ""), format="%d-%m-%Y", errors="coerce")
    for c in ("easting", "northing"):
        out[c] = to_number(out[c])
    # 0,0 means "no location recorded"
    no_loc = (out["easting"] <= 0) | (out["northing"] <= 0)
    out.loc[no_loc, ["easting", "northing"]] = np.nan
    out["latitude"], out["longitude"] = bng_to_wgs84(out["easting"], out["northing"])
    for c in ("lsoa_code", "district_code", "la_code", "region", "la_name"):
        out[c] = out[c].replace({"": None, "Not Applicable": None, "Not applicable": None})
    out["school_type"] = [
        school_type_category(t, g) for t, g in zip(out["establishment_type"], out["type_group"])
    ]
    return out.drop_duplicates("urn").reset_index(drop=True)


def read_gias_links(path: Path) -> pd.DataFrame:
    raw = read_csv_any_encoding(path)
    out = pd.DataFrame({
        "urn": pd.to_numeric(raw[_pick(raw, "URN")], errors="coerce"),
        "link_urn": pd.to_numeric(raw[_pick(raw, "LinkURN")], errors="coerce"),
        "link_type": raw[_pick(raw, "LinkType")].str.strip(),
    }).dropna(subset=["urn", "link_urn"])
    out[["urn", "link_urn"]] = out[["urn", "link_urn"]].astype("int64")
    return out.reset_index(drop=True)


def find_latest(directory: Path, pattern: str) -> Path | None:
    files = sorted(directory.glob(pattern)) if directory.exists() else []
    return files[-1] if files else None


# ---------------------------------------------------------------------------
# English Indices of Deprivation (IoD2019 or IoD2025, LSOA level)
# ---------------------------------------------------------------------------

IMD_PATTERNS = {
    "lsoa_code": r"^LSOA code",
    "lsoa_name": r"^LSOA name",
    "district_code": r"^Local Authority District code",
    "district_name": r"^Local Authority District name",
    "imd_score": r"Index of Multiple Deprivation \(IMD\) Score",
    "imd_rank": r"Index of Multiple Deprivation \(IMD\) Rank",
    "imd_decile": r"Index of Multiple Deprivation \(IMD\) Decile",
    "idaci_score": r"\(IDACI\) Score",
    "idaci_decile": r"\(IDACI\) Decile",
    "population": r"^Total population",
}


def _read_imd_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".xlsx", ".xls"):
        # The IMD workbooks have a notes sheet first; take the sheet with LSOA codes.
        for sheet, df in pd.read_excel(path, sheet_name=None, dtype=str).items():
            if _pick_regex(df, IMD_PATTERNS["lsoa_code"]):
                return df.fillna("")
        raise ValueError(f"{path}: no sheet with an 'LSOA code' column")
    return read_csv_any_encoding(path)


def read_imd(path: Path) -> pd.DataFrame:
    raw = _read_imd_table(path)
    out = pd.DataFrame(index=raw.index)
    for field, pattern in IMD_PATTERNS.items():
        col = _pick_regex(raw, pattern)
        out[field] = raw[col] if col else None
    if out["lsoa_code"].isna().all():
        raise ValueError(f"{path}: couldn't find an 'LSOA code' column")
    for c in ("imd_score", "imd_rank", "imd_decile", "idaci_score", "idaci_decile", "population"):
        out[c] = to_number(out[c].fillna(""))

    if out["imd_score"].isna().all() and out["imd_rank"].notna().any():
        # File 1 only has ranks. Turn the rank into a 0-100 score where higher
        # = more deprived, so the analysis still has a continuous measure.
        n = out["imd_rank"].max()
        out["imd_score"] = 100 * (n - out["imd_rank"]) / (n - 1)
    if out["imd_decile"].isna().all() and out["imd_rank"].notna().any():
        out["imd_decile"] = np.ceil(10 * out["imd_rank"] / out["imd_rank"].max())
    out["imd_decile"] = out["imd_decile"].astype("Int64")
    out["idaci_decile"] = out["idaci_decile"].astype("Int64")
    out["lsoa_code"] = out["lsoa_code"].str.strip()
    return out.dropna(subset=["lsoa_code"]).drop_duplicates("lsoa_code").reset_index(drop=True)


# ---------------------------------------------------------------------------
# ONS Postcode Directory (optional): postcode -> LSOA fallback
# ---------------------------------------------------------------------------

def read_onspd(path: Path) -> pd.DataFrame:
    """Accepts ONSPD or NSPL. Uses the 2021 LSOA column if present, else 2011."""
    head = pd.read_csv(path, nrows=0, encoding="utf-8-sig")
    pc_col = _pick(head, "pcds", "pcd", "pcd7", "pcd8")
    lsoa_col = _pick(head, "lsoa21cd", "lsoa21", "lsoa11cd", "lsoa11")
    if not pc_col or not lsoa_col:
        raise ValueError(f"{path}: need a postcode column (pcds) and an LSOA column (lsoa21/lsoa11)")
    df = pd.read_csv(path, usecols=[pc_col, lsoa_col], dtype=str, encoding="utf-8-sig")
    return pd.DataFrame({
        "postcode": normalise_postcode(df[pc_col]),
        "lsoa_code": df[lsoa_col].str.strip(),
    }).dropna().drop_duplicates("postcode")
