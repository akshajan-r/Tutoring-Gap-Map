-- =============================================================================
-- 04_trends.sql: how gaps move across years, using window functions.
--
-- Years aren't evenly spaced: there are no school tables for 2019-20 or
-- 2020-21, and 2021-22 grades were deliberately more generous. So
-- "previous year" means the previous year with data (prev_year says which),
-- and comparing with the national gap (behind_national_disadv) is safer than
-- comparing raw scores across years.
-- =============================================================================

DROP VIEW IF EXISTS v_school_trends;
DROP VIEW IF EXISTS v_la_trends;
DROP VIEW IF EXISTS v_national_trends;

CREATE VIEW v_national_trends AS
SELECT
    n.*,
    LAG(n.academic_year) OVER (ORDER BY n.year_start) AS prev_year,
    n.att8_gap - LAG(n.att8_gap) OVER (ORDER BY n.year_start) AS change_att8_gap
FROM v_national_year n;


CREATE VIEW v_la_trends AS
WITH t AS (
    SELECT
        l.*,
        LAG(l.academic_year) OVER w AS prev_year,
        LAG(l.gap_vs_national) OVER w AS prev_gap_vs_national,
        l.gap_vs_national - LAG(l.gap_vs_national) OVER w AS change_gap_vs_national,
        l.behind_national_disadv - LAG(l.behind_national_disadv) OVER w AS change_behind_national_disadv,
        -- positive = the LA climbed the "biggest gap" table (got relatively worse)
        LAG(l.rank_gap_vs_national) OVER w - l.rank_gap_vs_national AS rank_change,
        AVG(l.gap_vs_national) OVER (PARTITION BY l.la_code ORDER BY l.year_start
                                     ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS gap_vs_national_3yr_avg,
        l.gap_vs_national - FIRST_VALUE(l.gap_vs_national) OVER w AS change_since_first_year,
        FIRST_VALUE(l.academic_year) OVER w AS first_year,
        ROW_NUMBER() OVER w AS year_index,
        ROW_NUMBER() OVER (PARTITION BY l.la_code ORDER BY l.year_start DESC) AS recency
    FROM v_la_year l
    WINDOW w AS (PARTITION BY l.la_code ORDER BY l.year_start)
)
SELECT
    t.*,
    CASE
        WHEN t.change_gap_vs_national IS NULL THEN NULL
        WHEN t.change_gap_vs_national <= -1 THEN 'Narrowing'
        WHEN t.change_gap_vs_national >= 1 THEN 'Widening'
        ELSE 'Stable'
    END AS trend,
    CASE WHEN t.recency = 1 THEN 1 ELSE 0 END AS is_latest_year
FROM t;


-- Per school, following the school across URN changes (lineage_id).
CREATE VIEW v_school_trends AS
SELECT
    s.*,
    LAG(s.academic_year) OVER w AS prev_year,
    s.gap_vs_national - LAG(s.gap_vs_national) OVER w AS change_gap_vs_national,
    s.att8_disadv - LAG(s.att8_disadv) OVER w AS change_att8_disadv,
    AVG(s.gap_vs_national) OVER (PARTITION BY s.lineage_id ORDER BY s.year_start
                                 ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS gap_vs_national_3yr_avg,
    ROW_NUMBER() OVER (PARTITION BY s.lineage_id ORDER BY s.year_start DESC) AS recency
FROM v_school_year s
WHERE s.is_state_mainstream = 1
WINDOW w AS (PARTITION BY s.lineage_id ORDER BY s.year_start);
