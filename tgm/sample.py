"""Generate a SYNTHETIC dataset in the same file layouts as the real sources.

This lets the whole pipeline, SQL and dashboard run (and be tested) without
downloading anything. Every school, LA, postcode and score here is made up.
The LA names are fictional and the postcodes use the unused "ZZ" area. Never
present these numbers as findings.

What the generator plants so the analysis has something to find:
  * LAs differ in deprivation and in how well disadvantaged pupils do
    (with a London-style advantage in one region)
  * ~3% of schools in deprived areas get a big boost for disadvantaged
    pupils, which the beating-the-odds query should pick up
  * academy conversions mid-series: most recorded in the GIAS links file, a
    few only matchable by postcode and name
  * suppressed cells (SUPP, NE, LOWCOV), percentages written as "23%",
    LA and national total rows, cp1252-encoded GIAS
"""
from __future__ import annotations

import string
from pathlib import Path

import numpy as np
import pandas as pd

from .config import KS4_YEARS

REGIONS = {
    # name: (centre easting, centre northing, number of LAs)
    "North East": (425000, 560000, 3),
    "North West": (360000, 430000, 5),
    "Yorkshire and the Humber": (440000, 440000, 4),
    "East Midlands": (470000, 330000, 4),
    "West Midlands": (395000, 290000, 4),
    "East of England": (560000, 260000, 4),
    "London": (530000, 180000, 6),
    "South East": (480000, 150000, 5),
    "South West": (300000, 120000, 4),
}
LA_NAMES = [
    "Northfell", "Coalbridge", "Saltmarsh", "Highmoor", "Westerby", "Kingsferry", "Millhaven",
    "Brackenridge", "Ashvale", "Dunmere", "Thornwick", "Elmstead", "Copperfield", "Ravensholm",
    "Larkmoor", "Fenbury", "Greywater", "Stoneleigh Vale", "Harrowgate Cross", "Marlow Fen",
    "Brightwell", "Oakhurst", "Kestrel Bay", "Hollowmere", "Riverside East", "Riverside West",
    "Camden Fields", "Southmoor", "Wyvern", "Penhallow", "Tamsworth", "Carrick Down",
    "Fairhaven", "Wolds End", "Linden Park", "Moorgate Hill", "Bramblecombe", "Easterleigh",
    "Silverdale Moss", "Hartwell",
]
SCHOOL_WORDS = ["Park", "Hill", "Valley", "Grange", "Meadow", "Brook", "Castle", "Moor",
                "Field", "Green", "Bridge", "Heath", "Lane", "Forest", "Abbey", "Priory"]
SCHOOL_SUFFIX = ["School", "High School", "Academy", "Community College", "School"]
YEAR_EFFECT = {2018: 0.0, 2021: 3.0, 2022: 1.0, 2023: 0.0, 2024: -0.3}


def _fmt(x, decimals=1, pct=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "NA"
    return f"{x:.0f}%" if pct else f"{x:.{decimals}f}"


def generate(out_dir: Path, seed: int = 42, years: list[str] | None = None) -> Path:
    rng = np.random.default_rng(seed)
    years = years or KS4_YEARS
    out_dir = Path(out_dir)

    # --- Local authorities, districts and LSOAs ---------------------------
    las, lsoas = [], []
    la_idx = 0
    for region, (e0, n0, n_las) in REGIONS.items():
        for _ in range(n_las):
            la_code = 801 + la_idx
            name = LA_NAMES[la_idx]
            dep = rng.normal(0.4 if region in ("North East", "North West", "London") else 0, 1)
            la_e, la_n = e0 + rng.normal(0, 35000), n0 + rng.normal(0, 35000)
            las.append(dict(la_code=la_code, la_name=name, region=region, dep=dep,
                            e=la_e, n=la_n,
                            eff_d=rng.normal(5 if region == "London" else 0, 2.5),
                            eff_nd=rng.normal(1 if region == "London" else 0, 1.5),
                            trend=rng.normal(0, 0.6)))
            for d in range(rng.integers(1, 3)):
                dist_code = f"X07{la_code:03d}{d}"
                for k in range(rng.integers(40, 80)):
                    score = rng.gamma(2.2, 9.5) * np.exp(0.35 * dep)
                    lsoas.append(dict(lsoa_code=f"X01{la_code:03d}{d}{k:03d}",
                                      lsoa_name=f"{name} {d + 1}{string.ascii_uppercase[k % 26]}{k:03d}",
                                      district_code=dist_code, district_name=f"{name} District {d + 1}",
                                      la_code=la_code, imd_score=min(score, 92.0),
                                      population=int(rng.integers(1200, 2600))))
            la_idx += 1
    las = pd.DataFrame(las)
    lsoas = pd.DataFrame(lsoas)
    lsoas["imd_rank"] = lsoas["imd_score"].rank(ascending=False, method="first").astype(int)
    lsoas["imd_decile"] = np.ceil(10 * lsoas["imd_rank"] / len(lsoas)).astype(int)
    lsoas["idaci_score"] = np.clip(lsoas["imd_score"] / 100 * 1.1 + rng.normal(0, 0.03, len(lsoas)), 0.005, 0.8)
    lsoas["idaci_rank"] = lsoas["idaci_score"].rank(ascending=False, method="first").astype(int)
    lsoas["idaci_decile"] = np.ceil(10 * lsoas["idaci_rank"] / len(lsoas)).astype(int)

    # --- Schools ----------------------------------------------------------
    types = [("Academy converter", "Academies", 0.45), ("Academy sponsor led", "Academies", 0.19),
             ("Community school", "Local authority maintained schools", 0.12),
             ("Voluntary aided school", "Local authority maintained schools", 0.06),
             ("Foundation school", "Local authority maintained schools", 0.04),
             ("Free schools", "Free Schools", 0.06), ("Community special school", "Special schools", 0.05),
             ("Other independent school", "Independent schools", 0.03)]
    probs = np.array([t[2] for t in types])
    schools = []
    urn = 100000
    for la in las.itertuples():
        la_lsoas = lsoas[lsoas["la_code"] == la.la_code]
        for s in range(rng.integers(8, 22)):
            urn += int(rng.integers(3, 40))
            lsoa = la_lsoas.iloc[rng.integers(len(la_lsoas))]
            t = types[rng.choice(len(types), p=probs)]
            w1, w2 = rng.choice(SCHOOL_WORDS, size=2, replace=False)
            nm = f"{w1} {w2} {rng.choice(SCHOOL_SUFFIX)}"
            if rng.random() < 0.08:
                nm = f"St {rng.choice(['Thérèse', 'Anne', 'Bede', 'Hilda', 'Aidan'])}'s Catholic {rng.choice(SCHOOL_SUFFIX)}"
            beacon = lsoa["imd_decile"] <= 3 and rng.random() < 0.07
            schools.append(dict(
                urn=urn, name=f"{la.la_name} {nm}" if rng.random() < 0.3 else nm,
                la_code=la.la_code, la_name=la.la_name, region=la.region,
                lsoa_code=lsoa["lsoa_code"], district_code=lsoa["district_code"],
                district_name=lsoa["district_name"], imd_score=lsoa["imd_score"],
                type=t[0], group=t[1],
                e=la.e + rng.normal(0, 9000), n=la.n + rng.normal(0, 9000),
                postcode=f"ZZ{la.la_code - 790} {rng.integers(1, 10)}{rng.choice(list('ABDEFGHJLNPQRSTUWXY'))}{rng.choice(list('ABDEFGHJLNPQRSTUWXY'))}",
                size=int(rng.integers(70, 300)),
                pct=float(np.clip(4 + 0.75 * lsoa["imd_score"] + rng.normal(0, 8), 2, 85)),
                eff=rng.normal(0, 3), beacon=12.0 if beacon else 0.0,
                open_date="01-09-1975", close_date="", status="Open",
                la_eff_d=la.eff_d, la_eff_nd=la.eff_nd, la_trend=la.trend,
            ))
    schools = pd.DataFrame(schools)

    # --- Academy conversions: new URN from a given year onwards ----------
    links = []
    gias_extra = []
    maintained = schools.index[schools["group"] == "Local authority maintained schools"].tolist()
    convert = rng.choice(maintained, size=min(12, len(maintained)), replace=False)
    urn_by_year = {}
    for i, idx in enumerate(convert):
        conv_year = int(rng.choice([2022, 2023, 2024]))
        old = schools.loc[idx]
        new_urn = 140000 + i * 7
        new_name = old["name"].replace(" School", " Academy") if " School" in old["name"] else old["name"] + " Academy"
        urn_by_year[old["urn"]] = (conv_year, new_urn)
        close = f"31-08-{conv_year}"
        schools.loc[idx, ["close_date", "status"]] = [close, "Closed"]
        gias_extra.append({**old.to_dict(), "urn": new_urn, "name": new_name, "type": "Academy converter",
                           "group": "Academies", "open_date": f"01-09-{conv_year}", "close_date": "",
                           "status": "Open"})
        if i >= 2:  # the first two conversions are missing from the links file
            links += [(old["urn"], new_urn, "Successor"), (new_urn, old["urn"], "Predecessor")]
    gias = pd.concat([schools, pd.DataFrame(gias_extra)], ignore_index=True)

    # A school whose KS4 URN is missing from GIAS, but which shares a postcode
    # with a closed GIAS record (so the location can be borrowed by postcode).
    candidates = schools.index[(schools["group"] == "Academies") & ~schools.index.isin(convert)]
    orphan = schools.loc[candidates[0]]
    orphan_ks4_urn = 199999

    # --- KS4 results ------------------------------------------------------
    for year in years:
        y0 = int(year[:4])
        rows = []
        for s in schools.itertuples():
            ks4_urn = s.urn
            if s.urn in urn_by_year and y0 >= urn_by_year[s.urn][0]:
                ks4_urn = urn_by_year[s.urn][1]
            if s.Index == orphan.name and y0 >= 2023:
                ks4_urn = orphan_ks4_urn
            special = s.group == "Special schools"
            indep = s.group == "Independent schools"
            tpup = max(8, int(s.size * rng.uniform(0.9, 1.1))) if not special else int(rng.integers(10, 40))
            pct = 0.0 if indep else float(np.clip(s.pct + rng.normal(0, 2), 0, 95))
            n_d = int(round(tpup * pct / 100))
            ye = YEAR_EFFECT.get(y0, 0.0) + s.la_trend * (y0 - 2018) / 3
            nd = 51 - 0.05 * s.imd_score + s.eff + s.la_eff_nd + ye + rng.normal(0, 2)
            d = (38 - 0.11 * s.imd_score - 0.07 * pct + s.eff + s.la_eff_d + ye + s.beacon
                 + rng.normal(0, 3.5 / np.sqrt(max(n_d, 1) / 20)))
            if special:
                nd, d = nd - 30, d - 30
            nd, d = float(np.clip(nd, 5, 85)), float(np.clip(d, 3, 80))
            allp = (n_d * d + (tpup - n_d) * nd) / tpup

            def basics(a):
                return 100 / (1 + np.exp(-(a - 42) / 6))

            supp_d = n_d < 6 or indep
            p8 = y0 < 2024  # no Progress 8 for 2024-25 (no KS2 baseline in 2020)
            row = {
                "RECTYPE": "2" if special else "1", "LEA": str(s.la_code), "ESTAB": str(4000 + s.Index),
                "URN": str(ks4_urn), "SCHNAME": s.name if ks4_urn == s.urn else (
                    gias.loc[gias["urn"] == ks4_urn, "name"].iat[0] if (gias["urn"] == ks4_urn).any()
                    else s.name),
                "TOWN": s.la_name, "PCODE": s.postcode,
                "NFTYPE": "IND" if indep else ("ACC" if "Academy" in s.type else "CY"),
                "TPUP": str(tpup), "TFSM6CLA1A": "NA" if indep else str(n_d),
                "PTFSM6CLA1A": "NA" if indep else _fmt(pct, pct=True),
                "TNOTFSM6CLA1A": "NA" if indep else str(tpup - n_d),
                "ATT8SCR": _fmt(allp),
                "ATT8SCR_FSM6CLA1A": "SUPP" if supp_d else _fmt(d),
                "ATT8SCR_NFSM6CLA1A": "SUPP" if (tpup - n_d) < 6 else _fmt(nd),
                "P8MEA": _fmt((allp - 46) / 12, 2) if p8 and not indep else "NE",
                "P8MEA_FSM6CLA1A": _fmt((d - 41) / 12, 2) if p8 and not supp_d else "NE",
                "P8MEA_NFSM6CLA1A": _fmt((nd - 48) / 12, 2) if p8 and not indep else "NE",
                "PTL2BASICS_94": _fmt(basics(allp), pct=True),
                "PTFSM6CLA1ABASICS_94": "SUPP" if supp_d else _fmt(basics(d), pct=True),
                "PTNOTFSM6CLA1ABASICS_94": _fmt(basics(nd), pct=True),
            }
            if rng.random() < 0.01 and not supp_d:
                row["ATT8SCR_FSM6CLA1A"] = "LOWCOV"
            rows.append(row)
        ks4 = pd.DataFrame(rows)
        # LA and national total rows, as in the real file (no URN).
        totals = [{"RECTYPE": "4", "LEA": str(c), "URN": "", "SCHNAME": ""} for c in las["la_code"]]
        totals.append({"RECTYPE": "5", "LEA": "", "URN": "", "SCHNAME": "England"})
        ks4 = pd.concat([ks4, pd.DataFrame(totals)], ignore_index=True).fillna("")
        path = out_dir / "ks4" / year / "england_ks4final.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        ks4.to_csv(path, index=False)

    # --- GIAS -------------------------------------------------------------
    gias_out = pd.DataFrame({
        "URN": gias["urn"], "LA (code)": gias["la_code"], "LA (name)": gias["la_name"],
        "EstablishmentNumber": range(4000, 4000 + len(gias)), "EstablishmentName": gias["name"],
        "TypeOfEstablishment (name)": gias["type"], "EstablishmentTypeGroup (name)": gias["group"],
        "EstablishmentStatus (name)": gias["status"], "OpenDate": gias["open_date"],
        "CloseDate": gias["close_date"], "PhaseOfEducation (name)": "Secondary",
        "StatutoryLowAge": 11, "StatutoryHighAge": 16, "Gender (name)": "Mixed",
        "ReligiousCharacter (name)": np.where(gias["name"].str.startswith("St "), "Roman Catholic", "Does not apply"),
        "AdmissionsPolicy (name)": "Non-selective", "Postcode": gias["postcode"],
        "GOR (name)": gias["region"], "DistrictAdministrative (code)": gias["district_code"],
        "DistrictAdministrative (name)": gias["district_name"], "UrbanRural (name)": "(England/Wales) Urban city and town",
        "Trusts (name)": np.where(gias["group"] == "Academies", "Sample Learning Trust", ""),
        "LSOA (code)": gias["lsoa_code"], "Easting": gias["e"].round().astype(int),
        "Northing": gias["n"].round().astype(int),
    })
    gias_dir = out_dir / "gias"
    gias_dir.mkdir(parents=True, exist_ok=True)
    gias_out.to_csv(gias_dir / "edubasealldata20260930.csv", index=False, encoding="cp1252")
    pd.DataFrame(links, columns=["URN", "LinkURN", "LinkType"]).assign(
        LinkName="", LinkEstablishedDate=""
    ).to_csv(gias_dir / "links_edubasealldata20260930.csv", index=False, encoding="cp1252")

    # --- IMD (IoD2019 File 7 layout) --------------------------------------
    imd_out = pd.DataFrame({
        "LSOA code (2011)": lsoas["lsoa_code"], "LSOA name (2011)": lsoas["lsoa_name"],
        "Local Authority District code (2019)": lsoas["district_code"],
        "Local Authority District name (2019)": lsoas["district_name"],
        "Index of Multiple Deprivation (IMD) Score": lsoas["imd_score"].round(3),
        "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": lsoas["imd_rank"],
        "Index of Multiple Deprivation (IMD) Decile (where 1 is most deprived 10% of LSOAs)": lsoas["imd_decile"],
        "Income Deprivation Affecting Children Index (IDACI) Score (rate)": lsoas["idaci_score"].round(3),
        "Income Deprivation Affecting Children Index (IDACI) Rank (where 1 is most deprived)": lsoas["idaci_rank"],
        "Income Deprivation Affecting Children Index (IDACI) Decile (where 1 is most deprived 10% of LSOAs)": lsoas["idaci_decile"],
        "Total population: mid 2015 (excluding prisoners)": lsoas["population"],
    })
    (out_dir / "imd").mkdir(parents=True, exist_ok=True)
    imd_out.to_csv(out_dir / "imd" / "File_7_SAMPLE_IoD_scores.csv", index=False)

    # Answer key for tests: the schools given a boost for disadvantaged pupils.
    schools.loc[schools["beacon"] > 0, ["urn", "name", "la_name"]].to_csv(
        out_dir / "answer_key_beating_odds.csv", index=False)
    (out_dir / "README.txt").write_text(
        "SYNTHETIC SAMPLE DATA generated by tgm.sample - not real schools or results.\n"
    )
    return out_dir
