"""The EES (tidy) KS4 format must give the same results as the old england_ks4final.csv."""
import numpy as np
import pandas as pd
import pytest

from tgm import clean
from tgm.load import read_ks4_results

GROUPS = [("Total", "Total", "", "ATT8SCR", "P8MEA", "PTL2BASICS_94", "TPUP"),
          ("Disadvantage status", "Disadvantaged", "_FSM6CLA1A", "ATT8SCR_FSM6CLA1A", "P8MEA_FSM6CLA1A",
           "PTFSM6CLA1ABASICS_94", "TFSM6CLA1A"),
          ("Disadvantage status", "Not known to be disadvantaged", "_NFSM6CLA1A", "ATT8SCR_NFSM6CLA1A",
           "P8MEA_NFSM6CLA1A", "PTNOTFSM6CLA1ABASICS_94", "TNOTFSM6CLA1A")]


def to_ees(ks4_dir, years):
    """Rewrite the sample's england_ks4final.csv files in the EES long layout."""
    rows = []
    for year in years:
        df = pd.read_csv(ks4_dir / year / "england_ks4final.csv", dtype=str, keep_default_na=False)
        df = df[df["RECTYPE"].isin(["1", "2"])]
        tp = year[:4] + year[-2:]
        for r in df.to_dict("records"):
            base = {"time_period": tp, "time_identifier": "Academic year", "geographic_level": "School",
                    "school_urn": r["URN"], "school_name": r["SCHNAME"],
                    "establishment_type_group": "Community special school" if r["RECTYPE"] == "2" else "Converter academies",
                    "sex": "Total", "first_language": "Total"}
            for topic, status, _, a8, p8, b94, n in GROUPS:
                rows.append({**base, "breakdown_topic": topic, "breakdown": status, "disadvantage_status": status,
                             "pupil_count": {"NA": "z"}.get(r[n], r[n]),
                             "attainment8_average": {"SUPP": "c", "LOWCOV": "x"}.get(r[a8], r[a8]),
                             "progress8_average": {"NE": "z", "SUPP": "c"}.get(r[p8], r[p8]),
                             "engmath_94_percent": r[b94].replace("%", "").replace("SUPP", "c")})
            # A breakdown the reader must ignore.
            rows.append({**base, "breakdown_topic": "Sex", "breakdown": "Boys", "disadvantage_status": "Total",
                         "sex": "Boys", "pupil_count": "1", "attainment8_average": "99",
                         "progress8_average": "9", "engmath_94_percent": "99"})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def ees_file(sample_dir, tmp_path_factory):
    path = tmp_path_factory.mktemp("ees") / "ees_ks4_schools.csv"
    to_ees(sample_dir / "ks4", ["2022-2023", "2023-2024", "2024-2025"]).to_csv(path, index=False)
    return path


def test_ees_reader_matches_old_format(sample_dir, ees_file):
    ees = clean.read_ees_ks4(ees_file).set_index(["year_start", "urn"]).sort_index()
    old = pd.concat([clean.read_ks4(sample_dir / "ks4" / y / "england_ks4final.csv", y)
                     for y in ["2022-2023", "2023-2024", "2024-2025"]]).set_index(["year_start", "urn"]).sort_index()
    assert ees.index.equals(old.index)
    for c in ["total_pupils", "n_disadv", "n_nondisadv", "att8_all", "att8_disadv", "att8_nondisadv",
              "p8_disadv", "basics94_disadv", "basics94_nondisadv", "is_special"]:
        np.testing.assert_allclose(ees[c].astype(float), old[c].astype(float), err_msg=c)
    # EES has no % column; it's computed from the counts.
    np.testing.assert_allclose(ees["pct_disadv"], 100 * old["n_disadv"].astype(float) / old["total_pupils"].astype(float))
    assert (ees["academic_year"] == old["academic_year"]).all()


def test_ees_slim_keeps_only_needed_rows(ees_file):
    raw = pd.read_csv(ees_file, dtype=str, keep_default_na=False)
    slim = clean.slim_ees_ks4(raw)
    assert set(slim["breakdown_topic"]) == {"Total", "Disadvantage status"}
    assert list(slim.columns) == clean.EES_KS4_COLUMNS


def test_ees_wins_and_older_years_fill_in(sample_dir, ees_file, tmp_path):
    ks4 = tmp_path / "ks4"
    for y in ["2018-2019", "2021-2022", "2022-2023"]:   # 2022-23 overlaps with EES
        (ks4 / y).mkdir(parents=True)
        (ks4 / y / "england_ks4final.csv").write_bytes((sample_dir / "ks4" / y / "england_ks4final.csv").read_bytes())
    (ks4 / "ees_ks4_schools.csv").write_bytes(ees_file.read_bytes())
    res = read_ks4_results(ks4)
    assert sorted(res["academic_year"].unique()) == ["2018-19", "2021-22", "2022-23", "2023-24", "2024-25"]
    assert not res.duplicated(["year_start", "urn"]).any()
    # 2022-23 came from EES: its pct_disadv is not a whole number everywhere
    pct = res.loc[res.year_start == 2022, "pct_disadv"].dropna()
    assert (pct % 1 != 0).any()
