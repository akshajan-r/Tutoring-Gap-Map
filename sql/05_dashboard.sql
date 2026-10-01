-- =============================================================================
-- 05_dashboard.sql: flat tables for Tableau Public / Power BI.
-- `python -m tgm export` writes each of these to CSV.
-- =============================================================================

DROP VIEW IF EXISTS dash_schools;
DROP VIEW IF EXISTS dash_local_authorities;

-- One row per state-funded mainstream school per year.
CREATE VIEW dash_schools AS
SELECT
    t.academic_year,
    t.year_start,
    t.urn,
    t.lineage_id,
    t.school_name,
    t.postcode,
    t.la_name,
    t.region,
    t.school_type,
    t.trust_name,
    t.urban_rural,
    t.latitude,
    t.longitude,
    t.imd_decile,
    t.idaci_decile,
    t.total_pupils,
    t.n_disadv,
    t.pct_disadv,
    t.reportable,
    t.att8_all,
    t.att8_disadv,
    t.att8_nondisadv,
    t.p8_disadv,
    t.basics94_disadv,
    t.basics94_nondisadv,
    t.gap_within_school,
    t.gap_vs_national,
    t.basics_gap_vs_national,
    t.national_att8_nondisadv,
    t.prev_year,
    t.change_gap_vs_national,
    t.gap_vs_national_3yr_avg,
    CASE WHEN t.recency = 1 THEN 1 ELSE 0 END AS is_latest_year,
    o.att8_disadv_expected,
    o.residual,
    o.residual_z,
    o.serves_deprived,
    COALESCE(o.beating_odds, 0) AS beating_odds
FROM v_school_trends t
LEFT JOIN v_school_odds o ON o.urn = t.urn AND o.year_start = t.year_start;


-- One row per local authority per year, with deprivation and a map point.
CREATE VIEW dash_local_authorities AS
SELECT
    t.academic_year,
    t.year_start,
    t.la_code,
    t.la_name,
    t.region,
    a.latitude,
    a.longitude,
    a.imd_score_avg,
    a.pct_pop_most_deprived_20,
    a.imd_rank_among_las,
    t.n_schools,
    t.n_pupils,
    t.n_disadv,
    t.pct_disadv,
    t.pct_disadv_covered,
    t.att8_disadv,
    t.att8_nondisadv,
    t.national_att8_nondisadv,
    t.gap_within_la,
    t.gap_vs_national,
    t.behind_national_disadv,
    t.basics94_disadv,
    t.basics_gap_vs_national,
    t.p8_disadv,
    t.scale_of_need,
    t.rank_gap_vs_national,
    t.rank_gap_within_la,
    t.rank_scale_of_need,
    t.rank_in_region,
    t.n_las_in_year,
    t.prev_year,
    t.change_gap_vs_national,
    t.rank_change,
    t.gap_vs_national_3yr_avg,
    t.change_since_first_year,
    t.first_year,
    t.trend,
    t.is_latest_year
FROM v_la_trends t
LEFT JOIN local_authorities a ON a.la_code = t.la_code;
