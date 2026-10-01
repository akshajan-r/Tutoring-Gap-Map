"""Join the cleaned sources on URN and postcode and load them into the database."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import clean, config
from .db import Database
from .lineage import build_lineage, name_similarity

SCHOOL_COLUMNS = [
    "urn", "lineage_id", "lineage_method", "school_name", "postcode", "la_code", "la_name",
    "region", "school_type", "establishment_type", "type_group", "phase", "gender",
    "religious_character", "admissions_policy", "urban_rural", "trust_name", "status",
    "open_date", "close_date", "lsoa_code", "district_code", "easting", "northing",
    "latitude", "longitude", "location_source",
]
# Fields borrowed from a same-postcode GIAS record when a URN is missing from GIAS.
_LOCATION_FIELDS = [
    "la_code", "la_name", "region", "lsoa_code", "district_code", "easting", "northing",
    "latitude", "longitude", "urban_rural",
]


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


# ---------------------------------------------------------------------------
# Reading raw inputs
# ---------------------------------------------------------------------------

def read_ks4_results(ks4_dir: Path) -> pd.DataFrame:
    """EES download for recent years, plus any hand-added england_ks4final.csv
    files for years EES doesn't cover (EES wins where both have a year)."""
    frames, sources = [], []
    ees_path = clean.find_latest(ks4_dir, "ees_*.csv")
    if ees_path:
        ees = clean.read_ees_ks4(ees_path)
        frames.append(ees)
        sources += [f"{y} (EES)" for y in sorted(ees["academic_year"].unique())]
    have = {y for f in frames for y in f["year_start"].unique()}
    for year, path in clean.find_ks4_files(ks4_dir).items():
        df = clean.read_ks4(path, year)
        if df["year_start"].iat[0] in have:
            continue
        frames.append(df)
        sources.append(f"{df['academic_year'].iat[0]} ({path.name})")
    if not frames:
        raise SystemExit(f"No KS4 results in {ks4_dir}: run `python -m tgm download`")
    results = pd.concat(frames, ignore_index=True).sort_values(["year_start", "urn"], ignore_index=True)
    log(f"KS4 results: {len(results):,} school-years: {', '.join(sorted(sources))}")
    return results


def read_inputs(raw_dir: Path) -> dict:
    results = read_ks4_results(raw_dir / "ks4")

    gias_path = clean.find_latest(raw_dir / "gias", "edubasealldata*.csv")
    if gias_path is None:
        raise SystemExit(f"No GIAS file found: {raw_dir / 'gias'}/edubasealldata*.csv")
    gias = clean.read_gias(gias_path)
    log(f"GIAS: {len(gias):,} establishments from {gias_path.name}")

    links_path = clean.find_latest(raw_dir / "gias", "links_edubasealldata*.csv")
    links = clean.read_gias_links(links_path) if links_path else None
    log(f"GIAS links: {len(links):,}" if links is not None else "GIAS links: none (URN changes "
        "will only be followed by postcode matching)")

    imd_files = sorted((raw_dir / "imd").glob("*.csv")) + sorted((raw_dir / "imd").glob("*.xlsx"))
    if not imd_files:
        raise SystemExit(f"No deprivation file found in {raw_dir / 'imd'}")
    imd = clean.read_imd(imd_files[0])
    log(f"IMD: {len(imd):,} LSOAs from {imd_files[0].name}")

    onspd_path = clean.find_latest(raw_dir / "onspd", "*.csv")
    onspd = clean.read_onspd(onspd_path) if onspd_path else None
    return {"results": results, "gias": gias, "links": links, "imd": imd, "onspd": onspd}


# ---------------------------------------------------------------------------
# Joins
# ---------------------------------------------------------------------------

def match_missing_by_postcode(missing: pd.DataFrame, gias: pd.DataFrame) -> pd.DataFrame:
    """For KS4 URNs absent from GIAS, borrow location fields from the GIAS
    establishment at the same postcode with the most similar name."""
    cand = missing.merge(gias, left_on="ks4_postcode", right_on="postcode",
                         suffixes=("", "_gias"))
    if cand.empty:
        return cand
    cand["sim"] = [name_similarity(a, b) for a, b in zip(cand["ks4_school_name"], cand["school_name"])]
    return cand.sort_values("sim", ascending=False).drop_duplicates("urn")


def build_schools(results: pd.DataFrame, gias: pd.DataFrame, links, onspd) -> pd.DataFrame:
    latest = (results.sort_values("year_start")
              .drop_duplicates("urn", keep="last")[["urn", "ks4_school_name", "ks4_postcode"]])
    schools = latest.merge(gias, on="urn", how="left", indicator=True)
    in_gias = schools["_merge"] == "both"
    schools["location_source"] = np.where(in_gias, "gias_urn", None)
    log(f"Joined on URN: {in_gias.sum():,}/{len(schools):,} schools found in GIAS")

    missing = schools.loc[~in_gias, ["urn", "ks4_school_name", "ks4_postcode"]]
    if len(missing):
        matched = match_missing_by_postcode(missing, gias)
        if len(matched):
            idx = schools.set_index("urn")
            for f in _LOCATION_FIELDS:
                idx.loc[matched["urn"].values, f] = matched[f].values
            idx.loc[matched["urn"].values, "location_source"] = "gias_postcode"
            schools = idx.reset_index()
        log(f"Joined on postcode: {len(matched):,}/{len(missing):,} schools missing from GIAS")

    schools["school_name"] = schools["school_name"].fillna(schools["ks4_school_name"])
    schools["postcode"] = schools["postcode"].fillna(schools["ks4_postcode"])
    schools["school_type"] = schools["school_type"].fillna("Other")

    if onspd is not None:
        need = schools["lsoa_code"].isna()
        pc_lsoa = schools.loc[need, "postcode"].map(onspd.set_index("postcode")["lsoa_code"])
        schools.loc[need, "lsoa_code"] = pc_lsoa
        log(f"LSOA from ONS postcode directory: {pc_lsoa.notna().sum():,} schools")

    lineage = build_lineage(gias, links, results)
    schools = schools.merge(lineage, on="urn", how="left")
    n_linked = (schools["lineage_method"] != "self").sum()
    log(f"URN lineage: {n_linked:,} URNs chained to a predecessor/successor "
        f"({(schools['lineage_method'] == 'postcode_match').sum():,} by postcode)")
    for c in ("open_date", "close_date"):
        schools[c] = pd.to_datetime(schools[c]).dt.strftime("%Y-%m-%d")
    return schools[SCHOOL_COLUMNS]


def build_local_authorities(schools: pd.DataFrame, gias: pd.DataFrame,
                            imd: pd.DataFrame) -> pd.DataFrame:
    """Education LAs (upper tier) with population-weighted deprivation.

    IMD is published by lower-tier district; GIAS tells us which education LA
    each district's schools belong to, which gives the district -> LA mapping.
    """
    def mode(s):
        s = s.dropna()
        return s.mode().iat[0] if len(s) else None

    d2la = (gias.dropna(subset=["district_code", "la_code"])
            .groupby("district_code")["la_code"].agg(mode))

    lsoa = imd.copy()
    lsoa["la_code"] = lsoa["district_code"].map(d2la)
    lsoa["w"] = lsoa["population"].fillna(1.0) if lsoa["population"].notna().any() else 1.0
    lsoa["w_score"] = lsoa["w"] * lsoa["imd_score"]
    lsoa["w_deprived"] = lsoa["w"] * (lsoa["imd_decile"] <= 2).astype(float)
    agg = lsoa.dropna(subset=["la_code"]).groupby("la_code")[["w", "w_score", "w_deprived"]].sum()
    dep = pd.DataFrame({
        "imd_score_avg": agg["w_score"] / agg["w"],
        "pct_pop_most_deprived_20": 100 * agg["w_deprived"] / agg["w"],
    })

    las = (schools.dropna(subset=["la_code"]).groupby("la_code")
           .agg(la_name=("la_name", mode), region=("region", mode),
                latitude=("latitude", "mean"), longitude=("longitude", "mean"),
                n_schools=("urn", "nunique")))
    las = las.join(dep, how="left").reset_index()
    las["imd_rank_among_las"] = las["imd_score_avg"].rank(ascending=False, method="min").astype("Int64")
    return las


def lsoa_table(imd: pd.DataFrame) -> pd.DataFrame:
    return imd[["lsoa_code", "lsoa_name", "district_code", "district_name", "imd_score",
                "imd_rank", "imd_decile", "idaci_score", "idaci_decile", "population"]]


def params_table() -> pd.DataFrame:
    return pd.DataFrame([
        ("min_disadv_cohort", config.MIN_DISADV_COHORT),
        ("beating_odds_z", config.BEATING_ODDS_Z),
        ("deprived_imd_decile", config.DEPRIVED_IMD_DECILE),
        ("deprived_pct_disadv", config.DEPRIVED_PCT_DISADV),
    ], columns=["name", "value"]).astype({"value": float})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build(raw_dir: Path, db_target: str) -> Database:
    print(f"Reading raw files from {raw_dir}")
    inputs = read_inputs(raw_dir)
    results, gias, imd = inputs["results"], inputs["gias"], inputs["imd"]

    print("Joining")
    schools = build_schools(results, gias, inputs["links"], inputs["onspd"])
    has_loc = schools["latitude"].notna().mean()
    imd_match = schools["lsoa_code"].isin(imd["lsoa_code"]).mean()
    log(f"Schools with a map location: {has_loc:.1%}")
    log(f"Schools whose LSOA matched the deprivation file: {imd_match:.1%}")
    if imd_match < 0.9:
        log("WARNING: low LSOA match. GIAS may use 2021 LSOA codes while your IMD file "
            "uses 2011 codes (IoD2019). Use IoD2025, or add an ONS postcode directory "
            "with the matching LSOA vintage to data/raw/onspd/.")
    las = build_local_authorities(schools, gias, imd)

    ks4 = results.drop(columns=["ks4_school_name", "ks4_postcode"])

    db = Database(db_target)
    print(f"Loading into {db.kind}: {db.label}")
    db.drop_views()
    for name, df in [("schools", schools), ("ks4_results", ks4), ("lsoa_deprivation", lsoa_table(imd)),
                     ("local_authorities", las), ("analysis_params", params_table())]:
        db.write(df, name)
        log(f"{name}: {len(df):,} rows")
    print("Creating analysis views")
    db.create_views()
    log(", ".join(db.view_names()))
    return db
