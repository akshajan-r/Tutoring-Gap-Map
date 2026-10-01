-- =============================================================================
-- 01_base.sql: one row per school per year, joined to deprivation, plus the
-- England benchmark each year.
--
-- Written to run unchanged on SQLite (3.30+) and PostgreSQL.
--
-- Measures (Attainment 8 is out of 90; divide by 10 for an average grade):
--   gap_within_school  non-disadvantaged minus disadvantaged pupils, same school
--   gap_vs_national    national non-disadvantaged average minus this school's
--                      disadvantaged pupils. This is how DfE frames the gap, and
--                      it doesn't hide need in schools where everyone scores low.
-- =============================================================================

DROP VIEW IF EXISTS v_school_year;
DROP VIEW IF EXISTS v_national_year;
DROP VIEW IF EXISTS v_school_base;

CREATE VIEW v_school_base AS
SELECT
    r.academic_year,
    r.year_start,
    r.urn,
    s.lineage_id,
    s.school_name,
    s.postcode,
    s.la_code,
    s.la_name,
    s.region,
    s.school_type,
    s.establishment_type,
    s.trust_name,
    s.gender,
    s.religious_character,
    s.admissions_policy,
    s.urban_rural,
    s.latitude,
    s.longitude,
    s.lsoa_code,
    d.imd_score,
    d.imd_decile,
    d.idaci_score,
    d.idaci_decile,
    r.total_pupils,
    r.n_disadv,
    r.n_nondisadv,
    r.pct_disadv,
    r.att8_all,
    r.att8_disadv,
    r.att8_nondisadv,
    r.p8_all,
    r.p8_disadv,
    r.p8_nondisadv,
    r.basics94_all,
    r.basics94_disadv,
    r.basics94_nondisadv,
    CASE WHEN r.is_special = 0 AND s.school_type NOT IN ('Special', 'Independent')
         THEN 1 ELSE 0 END AS is_state_mainstream,
    -- Enough disadvantaged pupils for the school's figures to mean something.
    CASE WHEN r.n_disadv >= (SELECT value FROM analysis_params WHERE name = 'min_disadv_cohort')
         THEN 1 ELSE 0 END AS reportable
FROM ks4_results r
JOIN schools s ON s.urn = r.urn
LEFT JOIN lsoa_deprivation d ON d.lsoa_code = s.lsoa_code;


-- England benchmark: state-funded mainstream schools, weighted by pupil numbers
-- (each average only counts schools where that figure was published).
CREATE VIEW v_national_year AS
WITH w AS (
    SELECT
        academic_year,
        year_start,
        COUNT(*) AS n_schools,
        SUM(total_pupils) AS n_pupils,
        SUM(n_disadv) AS n_disadv,
        SUM(CASE WHEN att8_disadv IS NOT NULL THEN n_disadv * att8_disadv END)
            / NULLIF(SUM(CASE WHEN att8_disadv IS NOT NULL THEN n_disadv END), 0) AS att8_disadv,
        SUM(CASE WHEN att8_nondisadv IS NOT NULL THEN n_nondisadv * att8_nondisadv END)
            / NULLIF(SUM(CASE WHEN att8_nondisadv IS NOT NULL THEN n_nondisadv END), 0) AS att8_nondisadv,
        SUM(CASE WHEN basics94_disadv IS NOT NULL THEN n_disadv * basics94_disadv END)
            / NULLIF(SUM(CASE WHEN basics94_disadv IS NOT NULL THEN n_disadv END), 0) AS basics94_disadv,
        SUM(CASE WHEN basics94_nondisadv IS NOT NULL THEN n_nondisadv * basics94_nondisadv END)
            / NULLIF(SUM(CASE WHEN basics94_nondisadv IS NOT NULL THEN n_nondisadv END), 0) AS basics94_nondisadv
    FROM v_school_base
    WHERE is_state_mainstream = 1
    GROUP BY academic_year, year_start
)
SELECT
    w.*,
    100.0 * n_disadv / NULLIF(n_pupils, 0) AS pct_disadv,
    att8_nondisadv - att8_disadv AS att8_gap,
    basics94_nondisadv - basics94_disadv AS basics94_gap
FROM w;


CREATE VIEW v_school_year AS
SELECT
    b.*,
    b.att8_nondisadv - b.att8_disadv AS gap_within_school,
    n.att8_nondisadv - b.att8_disadv AS gap_vs_national,
    n.basics94_nondisadv - b.basics94_disadv AS basics_gap_vs_national,
    n.att8_disadv AS national_att8_disadv,
    n.att8_nondisadv AS national_att8_nondisadv
FROM v_school_base b
JOIN v_national_year n ON n.year_start = b.year_start;
