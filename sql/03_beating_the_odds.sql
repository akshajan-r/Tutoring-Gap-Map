-- =============================================================================
-- 03_beating_the_odds.sql: schools whose disadvantaged pupils do much better
-- than the school's deprivation would predict.
--
-- For each year we fit, in plain SQL, an ordinary least squares regression:
--
--   att8_disadv ~ b0 + b_imd * imd_score + b_pct * pct_disadv
--
--   imd_score   deprivation of the neighbourhood the school sits in (IMD, LSOA)
--   pct_disadv  share of the year group who are disadvantaged (the intake)
--
-- With two predictors the OLS solution has a closed form in centred sums of
-- squares, so it needs no stats package. The residual (actual minus expected)
-- is scaled by its standard deviation to give residual_z.
--
-- Selective (grammar) schools are left out of the model: they admit pupils by
-- ability, so their disadvantaged pupils are not comparable with other schools'.
--
-- A school is "beating the odds" in a year when it:
--   * is state-funded, mainstream, non-selective, with >= min_disadv_cohort
--     disadvantaged pupils,
--   * serves a deprived community: either it sits in IMD decile <= deprived_imd_decile
--     AND >= deprived_area_min_pct_disadv % of its pupils are disadvantaged, or
--     >= deprived_pct_disadv % of its pupils are disadvantaged wherever it is, and
--   * has residual_z >= beating_odds_z.
-- All thresholds come from the analysis_params table.
-- =============================================================================

DROP VIEW IF EXISTS v_beating_the_odds;
DROP VIEW IF EXISTS v_school_odds;

CREATE VIEW v_school_odds AS
WITH p AS (
    SELECT
        MAX(CASE WHEN name = 'beating_odds_z' THEN value END) AS z_threshold,
        MAX(CASE WHEN name = 'deprived_imd_decile' THEN value END) AS deprived_decile,
        MAX(CASE WHEN name = 'deprived_pct_disadv' THEN value END) AS deprived_pct,
        MAX(CASE WHEN name = 'deprived_area_min_pct_disadv' THEN value END) AS area_min_pct
    FROM analysis_params
),
eligible AS (
    SELECT *
    FROM v_school_year
    WHERE is_state_mainstream = 1
      AND COALESCE(admissions_policy, '') <> 'Selective'
      AND reportable = 1
      AND att8_disadv IS NOT NULL
      AND imd_score IS NOT NULL
      AND pct_disadv IS NOT NULL
),
means AS (
    SELECT
        year_start,
        COUNT(*) AS n,
        AVG(imd_score) AS mx1,
        AVG(pct_disadv) AS mx2,
        AVG(att8_disadv) AS my
    FROM eligible
    GROUP BY year_start
),
sums AS (
    SELECT
        e.year_start,
        SUM((e.imd_score - m.mx1) * (e.imd_score - m.mx1)) AS s11,
        SUM((e.pct_disadv - m.mx2) * (e.pct_disadv - m.mx2)) AS s22,
        SUM((e.imd_score - m.mx1) * (e.pct_disadv - m.mx2)) AS s12,
        SUM((e.imd_score - m.mx1) * (e.att8_disadv - m.my)) AS s1y,
        SUM((e.pct_disadv - m.mx2) * (e.att8_disadv - m.my)) AS s2y
    FROM eligible e
    JOIN means m ON m.year_start = e.year_start
    GROUP BY e.year_start
),
coef AS (
    SELECT
        m.year_start,
        m.n,
        m.mx1,
        m.mx2,
        m.my,
        (s.s22 * s.s1y - s.s12 * s.s2y) / NULLIF(s.s11 * s.s22 - s.s12 * s.s12, 0) AS b_imd,
        (s.s11 * s.s2y - s.s12 * s.s1y) / NULLIF(s.s11 * s.s22 - s.s12 * s.s12, 0) AS b_pct
    FROM means m
    JOIN sums s ON s.year_start = m.year_start
),
resid AS (
    SELECT
        e.*,
        c.n AS n_in_model,
        c.b_imd,
        c.b_pct,
        c.my - c.b_imd * c.mx1 - c.b_pct * c.mx2 AS b0,
        c.my + c.b_imd * (e.imd_score - c.mx1) + c.b_pct * (e.pct_disadv - c.mx2) AS att8_disadv_expected,
        e.att8_disadv - (c.my + c.b_imd * (e.imd_score - c.mx1) + c.b_pct * (e.pct_disadv - c.mx2)) AS residual
    FROM eligible e
    JOIN coef c ON c.year_start = e.year_start
),
sd AS (
    -- residual standard error, n - 3 degrees of freedom (three fitted parameters)
    SELECT year_start, sqrt(SUM(residual * residual) / NULLIF(COUNT(*) - 3, 0)) AS resid_sd
    FROM resid
    GROUP BY year_start
),
flagged AS (
    SELECT
        r.*,
        sd.resid_sd,
        r.residual / NULLIF(sd.resid_sd, 0) AS residual_z,
        CASE WHEN (r.imd_decile <= p.deprived_decile AND r.pct_disadv >= p.area_min_pct)
                  OR r.pct_disadv >= p.deprived_pct
             THEN 1 ELSE 0 END AS serves_deprived,
        p.z_threshold
    FROM resid r
    JOIN sd ON sd.year_start = r.year_start
    CROSS JOIN p
)
SELECT
    f.*,
    CASE WHEN f.serves_deprived = 1 AND f.residual_z >= f.z_threshold THEN 1 ELSE 0 END AS beating_odds,
    RANK() OVER (PARTITION BY year_start ORDER BY residual DESC) AS rank_residual_england,
    RANK() OVER (PARTITION BY year_start, la_code ORDER BY residual DESC) AS rank_residual_in_la
FROM flagged f;


-- The list to learn from: one row per school (following URN changes), judged on
-- every year it was in the model, described as it was in its latest year.
CREATE VIEW v_beating_the_odds AS
WITH hist AS (
    SELECT
        o.*,
        COUNT(*) OVER (PARTITION BY lineage_id) AS years_in_model,
        SUM(beating_odds) OVER (PARTITION BY lineage_id) AS years_beating_odds,
        AVG(residual) OVER (PARTITION BY lineage_id) AS avg_residual,
        AVG(residual_z) OVER (PARTITION BY lineage_id) AS avg_residual_z,
        ROW_NUMBER() OVER (PARTITION BY lineage_id ORDER BY year_start DESC) AS recency
    FROM v_school_odds o
)
SELECT
    lineage_id,
    urn,
    school_name,
    la_code,
    la_name,
    region,
    school_type,
    trust_name,
    postcode,
    latitude,
    longitude,
    academic_year AS latest_year,
    imd_decile,
    pct_disadv,
    n_disadv,
    att8_disadv,
    att8_disadv_expected,
    residual,
    residual_z,
    gap_vs_national,
    gap_within_school,
    p8_disadv,
    basics94_disadv,
    beating_odds AS beating_odds_latest_year,
    years_in_model,
    years_beating_odds,
    avg_residual,
    avg_residual_z,
    CASE
        WHEN years_beating_odds >= 2 THEN 'Consistent (2+ years)'
        WHEN beating_odds = 1 THEN 'Latest year'
        ELSE 'Earlier year'
    END AS evidence
FROM hist
WHERE recency = 1
  AND serves_deprived = 1
  AND years_beating_odds >= 1;
