"""End-to-end on the synthetic sample: joins, SQL views and the planted signal."""
import numpy as np
import pandas as pd
import pytest

from tgm.dashboard import write_dashboard
from tgm.db import Database
from tgm.export import export


def test_tables_loaded(q):
    counts = q("""SELECT (SELECT COUNT(*) FROM schools) s, (SELECT COUNT(*) FROM ks4_results) r,
                         (SELECT COUNT(DISTINCT academic_year) FROM ks4_results) y""").iloc[0]
    assert counts.s > 400 and counts.r > 2000 and counts.y == 5


def test_every_school_has_location_and_deprivation(q):
    df = q("SELECT latitude, imd_score FROM v_school_base")
    assert df["latitude"].notna().all() and df["imd_score"].notna().all()


def test_urn_missing_from_gias_located_by_postcode(q):
    row = q("SELECT location_source, latitude FROM schools WHERE urn = 199999").iloc[0]
    assert row.location_source == "gias_postcode" and row.latitude is not None


def test_academy_conversions_followed(q):
    lin = q("SELECT lineage_method, COUNT(*) n FROM schools GROUP BY lineage_method").set_index("lineage_method")["n"]
    assert lin.get("gias_link", 0) >= 16        # 10 linked conversions, both URNs
    assert lin.get("postcode_match", 0) == 4    # 2 conversions missing from the links file
    # no lineage has two results in the same year
    assert q("SELECT lineage_id, year_start, COUNT(*) n FROM v_school_year "
             "GROUP BY lineage_id, year_start HAVING COUNT(*) > 1").empty


def test_totals_rows_and_special_schools_excluded_from_benchmark(q):
    nat = q("SELECT * FROM v_national_year")
    expected = q("SELECT year_start, COUNT(*) n FROM v_school_base WHERE is_state_mainstream = 1 GROUP BY year_start")
    assert nat.set_index("year_start")["n_schools"].equals(expected.set_index("year_start")["n"])
    assert (nat["att8_gap"] > 10).all()


def test_la_ranking_matches_pandas(q):
    s = q("SELECT * FROM v_school_year WHERE is_state_mainstream = 1 AND year_start = 2023")
    nat = q("SELECT att8_nondisadv FROM v_national_year WHERE year_start = 2023").iloc[0, 0]
    d = s.dropna(subset=["att8_disadv"])
    la = (d.assign(w=d.n_disadv * d.att8_disadv).groupby("la_code")
          .apply(lambda g: g.w.sum() / g.n_disadv.sum(), include_groups=False))
    expected = (nat - la).sort_values(ascending=False)
    got = q("SELECT la_code, gap_vs_national, rank_gap_vs_national FROM v_la_year "
            "WHERE year_start = 2023 ORDER BY rank_gap_vs_national")
    assert got["la_code"].tolist() == expected.index.tolist()
    np.testing.assert_allclose(got["gap_vs_national"], expected.values)
    assert got["rank_gap_vs_national"].tolist() == list(range(1, len(got) + 1))


def test_sql_regression_matches_numpy(q):
    for year in (2018, 2024):
        e = q(f"SELECT * FROM v_school_odds WHERE year_start = {year}")
        X = np.column_stack([np.ones(len(e)), e.imd_score, e.pct_disadv])
        beta, *_ = np.linalg.lstsq(X, e.att8_disadv, rcond=None)
        np.testing.assert_allclose(e[["b0", "b_imd", "b_pct"]].iloc[0], beta, rtol=1e-9)
        resid = e.att8_disadv - X @ beta
        np.testing.assert_allclose(e.residual, resid, atol=1e-9)
        np.testing.assert_allclose(e.resid_sd.iloc[0], np.sqrt((resid ** 2).sum() / (len(e) - 3)))


def test_beating_the_odds_recovers_planted_schools(q, sample_dir):
    key = pd.read_csv(sample_dir / "answer_key_beating_odds.csv")
    lin = q("SELECT urn, lineage_id, school_type FROM schools")
    key = key.merge(lin, on="urn")
    key = key[key.school_type != "Special"]             # specials are outside the model by design
    found = q("SELECT lineage_id FROM v_beating_the_odds WHERE evidence LIKE 'Consistent%'")
    recall = key.lineage_id.isin(found.lineage_id).mean()
    assert recall >= 0.8, f"recall {recall:.0%}"


def test_beating_the_odds_rules(q):
    bto = q("SELECT * FROM v_beating_the_odds")
    assert (bto.n_disadv >= 10).all()
    assert ((bto.imd_decile <= 3) | (bto.pct_disadv >= 40)).all()
    assert (bto.years_beating_odds >= 1).all() and bto.lineage_id.is_unique


def test_la_trend_window_functions(q):
    t = q("SELECT * FROM v_la_trends ORDER BY la_code, year_start")
    for _, g in t.groupby("la_code"):
        g = g.reset_index(drop=True)
        np.testing.assert_allclose(g.change_gap_vs_national[1:], np.diff(g.gap_vs_national))
        np.testing.assert_allclose(g.gap_vs_national_3yr_avg,
                                   g.gap_vs_national.rolling(3, min_periods=1).mean())
        assert g.prev_year[1:].tolist() == g.academic_year[:-1].tolist()
        assert g.is_latest_year.tolist() == [0] * (len(g) - 1) + [1]
    assert set(t.trend.dropna()) <= {"Narrowing", "Widening", "Stable"}


def test_export_and_dashboard(sqlite_db, tmp_path):
    db = Database(str(sqlite_db))
    frames = export(db, tmp_path / "out")
    for name in ("schools", "local_authorities", "beating_the_odds", "national"):
        assert (tmp_path / "out" / f"{name}.csv").exists() and len(frames[name])
    html = write_dashboard(db, tmp_path / "dash.html", synthetic=True).read_text()
    assert "const DATA = {" in html and "</script>" not in html.split("const DATA = ")[1].split(";\n")[0]
    db.close()


def test_static_site(sqlite_db, tmp_path, monkeypatch):
    from tgm.site import build_site
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/Tutoring-Gap-Map")
    db = Database(str(sqlite_db))
    index = build_site(db, tmp_path / "site", synthetic=True)
    db.close()
    html = index.read_text()
    for name in ("schools", "local_authorities", "beating_the_odds", "national"):
        assert (tmp_path / "site" / "data" / f"{name}.csv").exists()
        assert f'"data/{name}.csv"' in html                  # linked from the page
    assert "https://github.com/someone/Tutoring-Gap-Map" in html
    assert '"synthetic":true' in html                       # banner switched on
