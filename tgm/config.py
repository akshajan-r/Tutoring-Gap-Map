"""Paths, source URLs and analysis thresholds in one place."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SAMPLE_DIR = ROOT / "data" / "sample"
SQL_DIR = ROOT / "sql"
OUTPUT_DIR = ROOT / "outputs"
DEFAULT_DB = ROOT / "data" / "tutoring_gap.db"

# KS4 (GCSE) results come from DfE's Explore Education Statistics (EES) API:
# "Key stage 4 institution level - Schools (performance)", one tidy CSV with every
# school for the latest few years (2022/23-2024/25 as of 2026), split by
# disadvantage status. The old Compare School Performance site blocks scripted
# downloads, so earlier years (england_ks4final.csv) can only be added by hand.
EES_KS4_DATASET = "19e39901-a96c-be76-b9c2-6af54ae076d2"

# Years the synthetic sample generates (mirrors the published series: no
# school-level tables exist for 2019-20 or 2020-21, when exams were cancelled).
KS4_YEARS = ["2018-2019", "2021-2022", "2022-2023", "2023-2024", "2024-2025"]

# Raw layout. If downloading by hand, drop the files here:
#   data/raw/ks4/ees_ks4_schools.csv           (written by `python -m tgm download`)
#   data/raw/ks4/<year>/england_ks4final.csv   (optional older years, by hand)
#   data/raw/gias/edubasealldata<YYYYMMDD>.csv
#   data/raw/gias/links_edubasealldata<YYYYMMDD>.csv
#   data/raw/imd/<any IoD file with LSOA-level scores>.csv|.xlsx
#   data/raw/onspd/<optional ONS postcode directory>.csv

# Download sources. If one fails, `python -m tgm download` prints where to get it by hand.
SOURCES = {
    "ks4": {
        "landing": "https://explore-education-statistics.service.gov.uk/find-statistics/key-stage-4-performance",
        "url": f"https://api.education.gov.uk/statistics/v1/data-sets/{EES_KS4_DATASET}/csv",
        # Older years (england_ks4final.csv per year) - browser only.
        "older_years_landing": "https://www.compare-school-performance.service.gov.uk/download-data",
    },
    "gias": {
        "landing": "https://get-information-schools.service.gov.uk/Downloads",
        "url": "https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/edubasealldata{date}.csv",
        "links_url": "https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/links_edubasealldata{date}.csv",
    },
    "imd": {
        # English Indices of Deprivation 2025, File 7 ("all ranks, scores, deciles and
        # population denominators"): IMD and IDACI scores per LSOA. IoD2025 uses 2021
        # LSOA codes, which is what GIAS now gives each school (IoD2019 used 2011 codes
        # and matched only ~95% of schools).
        "landing": "https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025",
        "url": (
            "https://assets.publishing.service.gov.uk/media/691ded56d140bbbaa59a2a7d/"
            "File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv"
        ),
    },
}

# Analysis thresholds. These are written to the `analysis_params` table so the
# SQL views read them from the database rather than hard-coding them.
MIN_DISADV_COHORT = 10      # ignore schools with fewer disadvantaged pupils in the year group
BEATING_ODDS_Z = 1.0        # residual z-score needed to count as beating the odds
# "Serves a deprived community" (for beating the odds) means either:
DEPRIVED_IMD_DECILE = 3             # neighbourhood in IMD deciles 1-3 ...
DEPRIVED_AREA_MIN_PCT_DISADV = 25.0 # ... AND an intake at least this % disadvantaged (about the national rate)
DEPRIVED_PCT_DISADV = 40.0          # or, wherever it is, at least this % of the year group disadvantaged
# Selective (grammar) schools pick pupils by ability, so they are left out of the
# beating-the-odds model: their disadvantaged pupils are not a like-for-like group.
