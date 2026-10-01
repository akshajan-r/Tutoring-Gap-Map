"""The same SQL on Postgres must give the same answers as on SQLite."""
import numpy as np
import pandas as pd

from tgm.load import build

CHECKS = {
    "v_la_year": ("year_start, la_code", ["gap_vs_national", "gap_within_la", "rank_gap_vs_national", "scale_of_need"]),
    "v_school_odds": ("year_start, urn", ["att8_disadv_expected", "residual_z", "beating_odds"]),
    "v_beating_the_odds": ("lineage_id", ["years_beating_odds", "avg_residual_z"]),
    "v_la_trends": ("la_code, year_start", ["change_gap_vs_national", "gap_vs_national_3yr_avg", "rank_change"]),
}


def test_postgres_matches_sqlite(pg_url, sample_dir, q):
    db = build(sample_dir, pg_url)
    try:
        for view, (order, cols) in CHECKS.items():
            pg = db.query(f"SELECT {order}, {', '.join(cols)} FROM {view} ORDER BY {order}")
            lite = q(f"SELECT {order}, {', '.join(cols)} FROM {view} ORDER BY {order}")
            assert len(pg) == len(lite), view
            for c in cols:
                np.testing.assert_allclose(pd.to_numeric(pg[c]).astype(float),
                                           pd.to_numeric(lite[c]).astype(float), rtol=1e-9, err_msg=f"{view}.{c}")
    finally:
        db.close()
