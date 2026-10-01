import numpy as np
import pandas as pd
import pytest

from tgm import clean
from tgm.geo import bng_to_wgs84
from tgm.lineage import build_lineage, name_similarity, one_to_one_links


def test_to_number_handles_dfe_codes_and_percent_signs():
    s = pd.Series(["23%", "1,204", "SUPP", "NE", "LOWCOV", "x", "", "45.3", " 7 "])
    out = clean.to_number(s)
    assert out.tolist()[:2] == [23.0, 1204.0]
    assert out.iloc[2:7].isna().all()
    assert out.iloc[7] == 45.3 and out.iloc[8] == 7.0


def test_normalise_postcode():
    out = clean.normalise_postcode(pd.Series(["sw1a1aa", "SW1A  1AA", "m1 1ae", "", None, "X"]))
    assert out.tolist()[:3] == ["SW1A 1AA", "SW1A 1AA", "M1 1AE"]
    assert out.iloc[3:].isna().all()


def test_academic_year_label():
    assert clean.academic_year_label("2022-2023") == ("2022-23", 2022)
    assert clean.academic_year_label("2018-19") == ("2018-19", 2018)


def test_bng_to_wgs84_known_point():
    # Elizabeth Tower (Big Ben): TQ 30268 79640 -> 51.5007 N, 0.1246 W
    lat, lon = bng_to_wgs84([530268], [179640])
    assert lat[0] == pytest.approx(51.5007, abs=2e-4)
    assert lon[0] == pytest.approx(-0.1246, abs=2e-4)


def test_read_ks4_filters_totals_and_derives_counts(tmp_path):
    p = tmp_path / "england_ks4final.csv"
    pd.DataFrame({
        "RECTYPE": ["1", "2", "4", "5"],
        "LEA": ["201", "201", "201", ""],
        "URN": ["100001", "100002", "", ""],
        "SCHNAME": ["A School", "B Special", "", "England"],
        "PCODE": ["ab1 2cd", "AB1 2CE", "", ""],
        "TPUP": ["200", "20", "", ""],
        "PTFSM6CLA1A": ["25%", "SUPP", "", ""],
        "ATT8SCR_FSM6CLA1A": ["35.5", "SUPP", "", ""],
        "ATT8SCR_NFSM6CLA1A": ["50.1", "NE", "", ""],
    }).to_csv(p, index=False)
    df = clean.read_ks4(p, "2022-2023")
    assert sorted(df["urn"]) == [100001, 100002]
    a = df.set_index("urn").loc[100001]
    assert a["n_disadv"] == 50 and a["n_nondisadv"] == 150
    assert a["att8_disadv"] == 35.5 and a["ks4_postcode"] == "AB1 2CD"
    assert df.set_index("urn").loc[100002, "is_special"] == 1
    assert df["academic_year"].unique().tolist() == ["2022-23"]


@pytest.mark.parametrize("headers", [
    # IoD2019 File 7
    {"LSOA code (2011)": "lsoa", "Local Authority District code (2019)": "lad",
     "Index of Multiple Deprivation (IMD) Score": "score",
     "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "rank",
     "Index of Multiple Deprivation (IMD) Decile (where 1 is most deprived 10% of LSOAs)": "decile"},
    # IoD2025-style 2021 LSOAs
    {"LSOA code (2021)": "lsoa", "Local Authority District code (2024)": "lad",
     "Index of Multiple Deprivation (IMD) Score": "score",
     "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "rank",
     "Index of Multiple Deprivation (IMD) Decile (where 1 is most deprived 10% of LSOAs)": "decile"},
])
def test_read_imd_finds_columns_across_releases(tmp_path, headers):
    values = {"lsoa": ["E01000001", "E01000002"], "lad": ["E09000001"] * 2,
              "score": ["45.1", "5.2"], "rank": ["100", "30000"], "decile": ["1", "10"]}
    p = tmp_path / "imd.csv"
    pd.DataFrame({h: values[k] for h, k in headers.items()}).to_csv(p, index=False)
    out = clean.read_imd(p)
    assert out["lsoa_code"].tolist() == ["E01000001", "E01000002"]
    assert out["imd_score"].tolist() == [45.1, 5.2]
    assert out["imd_decile"].tolist() == [1, 10]


def test_read_imd_rank_only_file_gets_a_pseudo_score(tmp_path):
    p = tmp_path / "file1.csv"
    pd.DataFrame({"LSOA code (2011)": ["a", "b", "c"],
                  "Index of Multiple Deprivation (IMD) Rank": ["1", "2", "3"]}).to_csv(p, index=False)
    out = clean.read_imd(p)
    assert out["imd_score"].tolist() == [100.0, 50.0, 0.0]   # most deprived scores highest


def test_school_type_category():
    assert clean.school_type_category("Academy special converter", "Academies") == "Special"
    assert clean.school_type_category("Academy converter", "Academies") == "Academy (converter)"
    assert clean.school_type_category("Community school", "Local authority maintained schools") == "LA maintained"
    assert clean.school_type_category("University technical college", "Free Schools") == "Free school / UTC / studio"
    assert clean.school_type_category("Other independent school", "Independent schools") == "Independent"


def test_one_to_one_links_drops_merges_and_many_to_one():
    links = pd.DataFrame({
        "urn":      [1, 2, 3, 4, 5, 6],
        "link_urn": [2, 1, 9, 9, 7, 8],
        "link_type": ["Successor", "Predecessor", "Successor", "Successor",
                      "Successor - amalgamated", "Successor"],
    })
    pairs = one_to_one_links(links)
    assert set(map(tuple, pairs.values)) == {(1, 2), (6, 8)}  # 3,4 -> 9 is many-to-one


def test_name_similarity_ignores_generic_words():
    assert name_similarity("Hill Park School", "Hill Park Academy") == 1.0
    assert name_similarity("Hill Park School", "Valley Grange School") == 0.0


def test_lineage_refuses_same_year_clash():
    gias = pd.DataFrame({"urn": [1, 2], "postcode": [None, None], "school_name": ["a", "b"],
                         "close_date": pd.NaT, "open_date": pd.NaT})
    links = pd.DataFrame({"urn": [1], "link_urn": [2], "link_type": ["Successor"]})
    results = pd.DataFrame({"urn": [1, 2], "year_start": [2022, 2022]})
    out = build_lineage(gias, links, results).set_index("urn")
    assert out.loc[1, "lineage_id"] == 1 and out.loc[2, "lineage_id"] == 2
