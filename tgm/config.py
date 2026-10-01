"""Paths, source URLs and analysis thresholds in one place."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SAMPLE_DIR = ROOT / "data" / "sample"
SQL_DIR = ROOT / "sql"
OUTPUT_DIR = ROOT / "outputs"
DEFAULT_DB = ROOT / "data" / "tutoring_gap.db"

# Academic years with published KS4 school performance tables. There are no
# school-level tables for 2019-20 or 2020-21 (exams were cancelled for COVID).
KS4_YEARS = ["2018-2019", "2021-2022", "2022-2023", "2023-2024", "2024-2025"]

# Expected raw layout. If downloading by hand, drop the files here:
#   data/raw/ks4/<year>/england_ks4final.csv   (england_ks4revised/provisional also accepted)
#   data/raw/gias/edubasealldata<YYYYMMDD>.csv
#   data/raw/gias/links_edubasealldata<YYYYMMDD>.csv
#   data/raw/imd/<any IoD file with LSOA-level scores>.csv|.xlsx
#   data/raw/onspd/<optional ONS postcode directory>.csv
KS4_GLOB = "england_ks4*.csv"

# Best-effort download sources. Government download endpoints change often; if
# one fails, `python -m tgm download` prints the landing page to fetch from.
SOURCES = {
    "ks4": {
        "landing": "https://www.compare-school-performance.service.gov.uk/download-data",
        # The download form submits to this URL and returns a zip per year.
        "url": (
            "https://www.compare-school-performance.service.gov.uk/download-data"
            "?download=true&regions=0&filters=KS4&fileformat=csv&year={year}&meta=false"
        ),
    },
    "gias": {
        "landing": "https://get-information-schools.service.gov.uk/Downloads",
        "url": "https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/edubasealldata{date}.csv",
        "links_url": "https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/links_edubasealldata{date}.csv",
    },
    "imd": {
        # English Indices of Deprivation. File 7 ("all ranks, deciles and scores")
        # is the one we want: it has IMD and IDACI scores per LSOA.
        "landing": "https://www.gov.uk/government/collections/english-indices-of-deprivation",
        "url": (
            "https://assets.publishing.service.gov.uk/media/5dc407b440f0b6379a7acc8d/"
            "File_7_-_All_IoD2019_Scores__Ranks__Deciles_and_Population_Denominators_3.csv"
        ),
    },
}

# Analysis thresholds. These are written to the `analysis_params` table so the
# SQL views read them from the database rather than hard-coding them.
MIN_DISADV_COHORT = 10      # ignore schools with fewer disadvantaged pupils in the year group
BEATING_ODDS_Z = 1.0        # residual z-score needed to count as beating the odds
DEPRIVED_IMD_DECILE = 3     # "serves a deprived community": neighbourhood in IMD deciles 1-3 ...
DEPRIVED_PCT_DISADV = 40.0  # ... or at least this % of the year group is disadvantaged
