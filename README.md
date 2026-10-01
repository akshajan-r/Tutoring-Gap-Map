# Tutoring Gap Map

**Where do disadvantaged pupils in England fall furthest behind at GCSE, and which
schools serving deprived communities are beating the odds?**

This project builds a map of the GCSE attainment gap, for tutoring charities,
councils and individual tutors deciding where to send help. It uses free public
data only:

1. **Python pipeline** (`tgm/`): downloads and cleans DfE school results, school
   locations and deprivation data with pandas, joins them on school URN, postcode
   and neighbourhood (LSOA), and loads them into SQLite or Postgres.
2. **SQL analysis** (`sql/`): ranks local authorities by the gap, finds
   "beating the odds" schools with a regression written in plain SQL, and tracks
   trends with window functions. The same SQL runs on SQLite and Postgres.
3. **Dashboard**: exports for Tableau Public / Power BI, with step-by-step build
   guides in `dashboard/`, plus a generated interactive HTML preview.

```
python -m tgm all --sample     # try it now on synthetic data, no downloads
```

![Dashboard preview, synthetic data](docs/preview.png)
*Preview built from the synthetic sample: the areas, schools and numbers are made up.*

---

## Quick start

```bash
pip install -r requirements.txt

# 1. Try the whole thing on SYNTHETIC data (made-up schools, for testing)
python -m tgm all --sample
open outputs/tutoring_gap_map.html

# 2. Real data
python -m tgm download         # fetches what it can, prints manual steps for the rest
python -m tgm all              # build DB -> run SQL -> export -> HTML preview

# Postgres instead of SQLite
python -m tgm all --db postgresql://user:pass@localhost/tutoring_gap
```

Outputs:

| Path | What |
|---|---|
| `data/tutoring_gap.db` | SQLite database: tables + analysis views |
| `outputs/dashboard_data/*.csv`, `tutoring_gap_map.xlsx` | flat tables for Tableau Public / Power BI |
| `outputs/tutoring_gap_map.html` | self-contained interactive preview (map, rankings, trends, beating-the-odds list) |
| `outputs/site/` | `python -m tgm site`: the same page as `index.html` plus data downloads, ready to host |

## Publish it as a website (GitHub Pages)

The dashboard is a static page, so GitHub Pages can host it for free at
**https://akshajan-r.github.io/Tutoring-Gap-Map/**. The workflow in
[`.github/workflows/pages.yml`](.github/workflows/pages.yml) does the whole job on
GitHub's servers: install, test, download the public data, build the database, run the
SQL, write the site and deploy it.

1. Merge this branch into `main` (Pages deploys from the default branch).
2. Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. **Add the GCSE results files (once, then once a year).** The performance-tables site
   returns HTTP 403 to scripted downloads, including from GitHub's servers, so these
   are fetched in a browser and committed. GIAS and the deprivation index are still
   downloaded fresh by the workflow.
   - For each year, choose *All of England → Key stage 4 results → CSV*, unzip, and save
     `england_ks4final.csv` as `data/raw/ks4/<year>/england_ks4final.csv`
     (e.g. `data/raw/ks4/2023-2024/`). The years are listed in `tgm/config.py`.
   - Run `python -m tgm slim`. It cuts each file to the ~20 columns used, from several MB
     each to a fraction of that.
   - `git add data/raw/ks4 && git commit -m "Add KS4 results" && git push`
4. **Actions → Publish site → Run workflow.**
   - Leave *sample* unticked to publish real data. If any download fails, the run stops
     before publishing, and its log names the file and the page to get it from.
   - Tick *sample* to publish the synthetic demo straight away. It carries a
     "synthetic data" banner.

After that it rebuilds on the 2nd of each month (to pick up school openings, closures
and conversions from GIAS) and whenever the pipeline code on `main` changes. When a new
year's GCSE results come out, add the year to `KS4_YEARS` in `tgm/config.py` and repeat step 3. The site's footer lists the
sources, method and caveats, and links the CSVs for download.

To host it somewhere else (Netlify, a council intranet, etc.), run
`python -m tgm site` and upload the `outputs/site/` folder as-is.

## Data sources

All published under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

| Source | File | Used for |
|---|---|---|
| DfE school performance tables ([Compare School Performance download](https://www.compare-school-performance.service.gov.uk/download-data)) | `england_ks4final.csv` per year | Attainment 8, Progress 8 and English & maths 4+ for disadvantaged and other pupils |
| [Get Information About Schools](https://get-information-schools.service.gov.uk/Downloads) | `edubasealldataYYYYMMDD.csv`, `links_edubasealldataYYYYMMDD.csv` | location, LA, region, school type, LSOA; predecessor/successor URNs |
| [English Indices of Deprivation](https://www.gov.uk/government/collections/english-indices-of-deprivation) (IoD2019 or IoD2025) | LSOA-level file with scores (IoD2019 "File 7") | neighbourhood deprivation (IMD, IDACI) |
| [ONS Postcode Directory](https://geoportal.statistics.gov.uk/) *(optional)* | ONSPD / NSPL CSV | postcode → LSOA where GIAS has none |

If `python -m tgm download` can't reach a source (the endpoints change; the
script was written without being able to reach them), download by hand into:

```
data/raw/ks4/2023-2024/england_ks4final.csv      # one folder per academic year
data/raw/gias/edubasealldata20260930.csv
data/raw/gias/links_edubasealldata20260930.csv
data/raw/imd/<IoD LSOA scores>.csv  (or .xlsx)
data/raw/onspd/<postcode directory>.csv           # optional
```

On the performance-tables site choose *All of England → Key stage 4 results →
CSV* for each year. Years are set in `tgm/config.py`. The site blocks scripted
downloads (HTTP 403), so the KS4 files always come by hand. `python -m tgm slim`
shrinks them so they can be committed (`data/raw/ks4/` is the one raw folder git tracks).

## How the pipeline joins things

```
england_ks4final.csv ──URN──► GIAS establishment ──LSOA──► IMD (LSOA)
        │                         │                          │
        │ (URN not in GIAS?)      │ district code             └─► LA deprivation
        └──postcode + name──► GIAS record at same postcode        (pop-weighted)
GIAS links + postcode/name/date matching ──► lineage_id (follows academy conversions)
```

- **Cleaning**: DfE suppression codes (`SUPP`, `NE`, `LOWCOV`, `NP`, `x`, `c`, …) become
  NULL; `"23%"` becomes `23.0`; LA and national total rows are dropped; columns are found by
  name, not position, so different years' files all load.
- **URN → GIAS**: nearly every KS4 URN is in GIAS (it includes closed schools). Any that
  aren't borrow location, LA and LSOA from the GIAS record at the same **postcode** with the
  most similar name.
- **Following schools across URN changes**: academy conversion gives a school a new
  URN, which would break its trend. One-to-one predecessor/successor links from GIAS are
  chained into a `lineage_id`. Where GIAS has no link, a closure and an opening at the
  same postcode, within 60 days, with similar names, count as the same school. Merges
  and splits are left as separate lineages.
- **Locations**: GIAS gives British National Grid eastings/northings; `tgm/geo.py`
  converts them to WGS84 lat/long for mapping.
- **LA deprivation**: IMD is published by district; GIAS supplies the district → education-LA
  mapping, and LSOA scores are population-weighted up to LA level.

## How the measures work

Attainment 8 is out of 90 (divide by 10 ≈ average grade per subject). All
averages are **pupil-weighted** and use **state-funded mainstream** schools only
(special and independent schools are excluded).

| Measure | Definition | Why |
|---|---|---|
| `gap_vs_national` (headline) | national non-disadvantaged Att8 − disadvantaged Att8 here | DfE's framing; doesn't hide need in places where *everyone* scores low |
| `gap_within_la` / `gap_within_school` | non-disadvantaged − disadvantaged, same area/school | local inequality |
| `scale_of_need` | disadvantaged pupils × gap in grades per subject | where the most grades are missing in total: big LAs with moderate gaps can outrank small ones with big gaps |

"Disadvantaged" is DfE's definition: eligible for free school meals at any point
in the last 6 years, or looked after / previously looked after.

### Ranking local authorities (`sql/02_la_gap_ranking.sql`)
`v_la_year` aggregates schools to LA × year and ranks with `RANK() OVER (PARTITION BY year …)`
on all three measures, nationally and within region.

### Beating the odds (`sql/03_beating_the_odds.sql`)
For each year, an ordinary least squares regression is fitted **in SQL**
(closed-form, from centred sums of squares):

```
disadvantaged Att8 ≈ b0 + b_imd × neighbourhood IMD score + b_pct × % disadvantaged in the year group
```

A school's residual (actual − expected) is divided by the residual standard
deviation to give `residual_z`. A school is **beating the odds** in a year when it:

- has at least 10 disadvantaged pupils in the year group,
- serves a deprived community (IMD decile 1–3, or ≥40% disadvantaged), and
- has `residual_z ≥ 1`.

`v_beating_the_odds` then follows each school across years and URN changes:
**"Consistent (2+ years)"** is the list worth learning from, because one good year can be
luck. Thresholds live in the `analysis_params` table (set from `tgm/config.py`).
The test suite checks the SQL coefficients against numpy's least squares.

### Trends (`sql/04_trends.sql`)
`LAG` for change since the previous year with data, a 3-year rolling `AVG … ROWS BETWEEN 2 PRECEDING`,
`FIRST_VALUE` for change since the first year, and rank movement, for LAs and for schools by lineage.

## Caveats (please read before quoting numbers)

- **No 2019-20 or 2020-21 school tables** (exams cancelled), and 2021-22 grading was
  deliberately more generous. Compare gaps against the national gap rather than raw scores
  across years.
- **No Progress 8 for 2024-25** (and 2025-26): those cohorts had no KS2 tests in 2020/2021.
  The analysis uses Attainment 8, which is always available.
- **Suppression**: small cohorts are suppressed by DfE, so small schools drop out
  of school-level gap figures. `pct_disadv_covered` shows how much of an LA's
  disadvantaged cohort the LA figure covers.
- **IMD describes where a school is, not who attends.** That's why the regression also
  uses the school's own % disadvantaged.
- **LSOA vintages**: IoD2019 uses 2011 LSOAs and IoD2025 uses 2021 LSOAs. Use the IoD release
  that matches GIAS's LSOA codes. The build reports the match rate and warns if it's low.
- **Beating the odds is descriptive, not causal.** It flags schools worth a closer look
  (what are they doing?), not proof of what works.

## Using it for your own tutoring

Filter the dashboard to your region, or run `sql/example_queries.sql`
(query 5 lists every school in one LA, worst gap first). The beating-the-odds
schools near you are the ones to ask what's working.

## Dashboard

- **Tableau Public**: [`dashboard/TABLEAU.md`](dashboard/TABLEAU.md), with the calculated fields, sheets, filters and layout.
- **Power BI**: [`dashboard/POWERBI.md`](dashboard/POWERBI.md) and [`dashboard/measures.dax`](dashboard/measures.dax).
- **HTML preview**: `outputs/tutoring_gap_map.html`, generated by the pipeline. Filters for year,
  region, school type and measure, an LA bubble map with beating-the-odds schools,
  top-15 ranking, trend vs England, and the beating-the-odds table.

## Project layout

```
tgm/
  config.py      paths, years, source URLs, thresholds
  download.py    best-effort downloads
  clean.py       readers/cleaners for KS4, GIAS, IMD, ONSPD
  geo.py         British National Grid -> lat/long
  lineage.py     follow schools across URN changes
  load.py        joins + load into SQLite/Postgres + create views
  db.py          SQLite/Postgres wrapper
  export.py      CSV/xlsx extracts for Tableau / Power BI
  dashboard.py   HTML preview
  site.py        static website for GitHub Pages
  sample.py      SYNTHETIC data generator in the real file layouts
sql/
  01_base.sql              school-year view + England benchmark
  02_la_gap_ranking.sql    LA rankings
  03_beating_the_odds.sql  regression + beating-the-odds list
  04_trends.sql            window-function trends
  05_dashboard.sql         flat views behind the exports
  example_queries.sql      ad-hoc questions
dashboard/       Tableau + Power BI build guides, DAX
tests/           unit + end-to-end tests (incl. Postgres parity)
.github/workflows/pages.yml   build from public data + deploy to GitHub Pages
```

## Tests

```bash
python -m pytest
# include the Postgres parity test:
TGM_TEST_PG_URL=postgresql://user:pass@localhost/db python -m pytest
```

The end-to-end tests run on the synthetic sample. They check the joins (including
the postcode fallbacks), that LA rankings match a pandas recomputation, that the
SQL regression matches numpy, that the trend windows match pandas, that planted
"beating the odds" schools are recovered, and that Postgres returns the same
results as SQLite.
