-- =============================================================================
-- 02_la_gap_ranking.sql: rank local authorities by the disadvantage gap.
--
-- One row per education LA per year, state-funded mainstream schools only,
-- pupil-weighted. Three rankings, because they answer different questions:
--   rank_gap_vs_national   where disadvantaged pupils are furthest behind
--                          (national non-disadvantaged average minus LA disadvantaged)
--   rank_gap_within_la     where the local gap between the two groups is widest
--   rank_scale_of_need     where the most grades are missing in total
--                          (pupils x grades behind), which matters when
--                          deciding where to send tutors
-- =============================================================================

DROP VIEW IF EXISTS v_la_year;

CREATE VIEW v_la_year AS
WITH la AS (
    SELECT
        academic_year,
        year_start,
        la_code,
        MAX(la_name) AS la_name,
        MAX(region) AS region,
        COUNT(*) AS n_schools,
        SUM(total_pupils) AS n_pupils,
        SUM(n_disadv) AS n_disadv,
        SUM(CASE WHEN att8_disadv IS NOT NULL THEN n_disadv END) AS n_disadv_published,
        SUM(CASE WHEN att8_disadv IS NOT NULL THEN n_disadv * att8_disadv END)
            / NULLIF(SUM(CASE WHEN att8_disadv IS NOT NULL THEN n_disadv END), 0) AS att8_disadv,
        SUM(CASE WHEN att8_nondisadv IS NOT NULL THEN n_nondisadv * att8_nondisadv END)
            / NULLIF(SUM(CASE WHEN att8_nondisadv IS NOT NULL THEN n_nondisadv END), 0) AS att8_nondisadv,
        SUM(CASE WHEN basics94_disadv IS NOT NULL THEN n_disadv * basics94_disadv END)
            / NULLIF(SUM(CASE WHEN basics94_disadv IS NOT NULL THEN n_disadv END), 0) AS basics94_disadv,
        SUM(CASE WHEN p8_disadv IS NOT NULL THEN n_disadv * p8_disadv END)
            / NULLIF(SUM(CASE WHEN p8_disadv IS NOT NULL THEN n_disadv END), 0) AS p8_disadv
    FROM v_school_year
    WHERE is_state_mainstream = 1
      AND la_code IS NOT NULL
    GROUP BY academic_year, year_start, la_code
),
g AS (
    SELECT
        la.*,
        100.0 * la.n_disadv / NULLIF(la.n_pupils, 0) AS pct_disadv,
        100.0 * la.n_disadv_published / NULLIF(la.n_disadv, 0) AS pct_disadv_covered,
        la.att8_nondisadv - la.att8_disadv AS gap_within_la,
        n.att8_nondisadv - la.att8_disadv AS gap_vs_national,
        n.att8_disadv - la.att8_disadv AS behind_national_disadv,
        n.basics94_nondisadv - la.basics94_disadv AS basics_gap_vs_national,
        -- Attainment 8 / 10 ~ average grade, so this is pupils x grades behind per subject.
        la.n_disadv_published * (n.att8_nondisadv - la.att8_disadv) / 10.0 AS scale_of_need,
        n.att8_disadv AS national_att8_disadv,
        n.att8_nondisadv AS national_att8_nondisadv
    FROM la
    JOIN v_national_year n ON n.year_start = la.year_start
)
SELECT
    g.*,
    RANK() OVER (PARTITION BY year_start ORDER BY gap_vs_national DESC NULLS LAST) AS rank_gap_vs_national,
    RANK() OVER (PARTITION BY year_start ORDER BY gap_within_la DESC NULLS LAST) AS rank_gap_within_la,
    RANK() OVER (PARTITION BY year_start ORDER BY scale_of_need DESC NULLS LAST) AS rank_scale_of_need,
    RANK() OVER (PARTITION BY year_start, region ORDER BY gap_vs_national DESC NULLS LAST) AS rank_in_region,
    COUNT(*) OVER (PARTITION BY year_start) AS n_las_in_year
FROM g;
