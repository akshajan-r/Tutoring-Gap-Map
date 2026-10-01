"""Print a short summary of a real-data build (used by the temporary check workflow)."""
import sqlite3
import sys

import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
con = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else "data/tutoring_gap.db")
q = lambda s: pd.read_sql_query(s, con)

print("\n## Rows per year")
print(q("""SELECT academic_year, COUNT(*) schools, SUM(is_state_mainstream) mainstream,
                  SUM(CASE WHEN att8_disadv IS NOT NULL THEN 1 ELSE 0 END) with_disadv_att8,
                  SUM(CASE WHEN imd_score IS NULL THEN 1 ELSE 0 END) no_imd,
                  SUM(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END) no_location
           FROM v_school_base GROUP BY academic_year ORDER BY academic_year""").to_string(index=False))
print("\n## England (state-funded mainstream)")
print(q("SELECT academic_year, n_schools, ROUND(pct_disadv,1) pct_disadv, ROUND(att8_disadv,1) att8_disadv, "
        "ROUND(att8_nondisadv,1) att8_nondisadv, ROUND(att8_gap,1) gap FROM v_national_year ORDER BY year_start").to_string(index=False))
print("\n## Largest gaps, latest year")
print(q("SELECT rank_gap_vs_national rnk, la_name, region, n_disadv, ROUND(att8_disadv,1) att8_disadv, "
        "ROUND(gap_vs_national,1) gap_vs_nat, ROUND(gap_within_la,1) gap_within, ROUND(pct_disadv_covered) pct_cov, trend "
        "FROM v_la_trends WHERE is_latest_year = 1 ORDER BY rnk LIMIT 15").to_string(index=False))
print("\n## Smallest gaps, latest year")
print(q("SELECT rank_gap_vs_national rnk, la_name, region, ROUND(gap_vs_national,1) gap_vs_nat "
        "FROM v_la_trends WHERE is_latest_year = 1 ORDER BY rnk DESC LIMIT 5").to_string(index=False))
print("\n## Regression per year")
print(q("SELECT DISTINCT academic_year, n_in_model, ROUND(b0,2) b0, ROUND(b_imd,3) b_imd, "
        "ROUND(b_pct,3) b_pct, ROUND(resid_sd,2) resid_sd FROM v_school_odds ORDER BY academic_year").to_string(index=False))
print("\n## Beating the odds")
print(q("SELECT evidence, COUNT(*) n FROM v_beating_the_odds GROUP BY evidence").to_string(index=False))
print(q("SELECT school_name, la_name, imd_decile, ROUND(pct_disadv) pct_d, ROUND(att8_disadv,1) att8_d, "
        "ROUND(att8_disadv_expected,1) expected, years_beating_odds yrs, years_in_model of_yrs "
        "FROM v_beating_the_odds WHERE evidence LIKE 'Consistent%' "
        "ORDER BY years_beating_odds DESC, avg_residual_z DESC LIMIT 12").to_string(index=False))
print("\n## Lineage")
print(q("SELECT lineage_method, location_source, COUNT(*) n FROM schools GROUP BY 1, 2").to_string(index=False))
