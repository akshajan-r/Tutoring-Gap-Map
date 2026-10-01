-- Handy questions to ask the database once it's built. Each runs on SQLite and Postgres:
--   sqlite3 data/tutoring_gap.db < sql/example_queries.sql
-- (Not run by the pipeline: the file name doesn't start with a number.)

-- 1. The 10 LAs where disadvantaged pupils are furthest behind, latest year.
SELECT la_name, region, rank_gap_vs_national AS rnk,
       gap_vs_national, gap_within_la, n_disadv, trend
FROM v_la_trends
WHERE is_latest_year = 1
ORDER BY rank_gap_vs_national
LIMIT 10;

-- 2. Where to send tutors: biggest total shortfall (pupils x grades behind).
SELECT la_name, region, n_disadv, gap_vs_national, scale_of_need, rank_scale_of_need
FROM v_la_year
WHERE year_start = (SELECT MAX(year_start) FROM v_la_year)
ORDER BY rank_scale_of_need
LIMIT 10;

-- 3. LAs whose gap has widened two comparisons running.
WITH t AS (
    SELECT la_name, academic_year, change_gap_vs_national,
           LAG(change_gap_vs_national) OVER (PARTITION BY la_code ORDER BY year_start) AS prev_change
    FROM v_la_trends
)
SELECT * FROM t
WHERE change_gap_vs_national > 0 AND prev_change > 0
ORDER BY academic_year DESC, change_gap_vs_national DESC;

-- 4. Schools consistently beating the odds in one region.
SELECT school_name, la_name, school_type, imd_decile, pct_disadv,
       att8_disadv, att8_disadv_expected, years_beating_odds, years_in_model
FROM v_beating_the_odds
WHERE region = 'North East' AND evidence LIKE 'Consistent%'
ORDER BY years_beating_odds DESC, avg_residual_z DESC;

-- 5. Your own patch: every school in one LA, worst gap first (edit the name).
SELECT school_name, n_disadv, pct_disadv, att8_disadv, gap_vs_national,
       change_gap_vs_national, beating_odds
FROM dash_schools
WHERE la_name = 'Northfell' AND is_latest_year = 1
ORDER BY gap_vs_national DESC NULLS LAST;

-- 6. The regression behind "beating the odds", one row per year.
SELECT DISTINCT academic_year, n_in_model, b0, b_imd, b_pct, resid_sd
FROM v_school_odds
ORDER BY academic_year;
