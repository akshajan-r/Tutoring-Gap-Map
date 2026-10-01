"""Write the dashboard views to CSV (and one Excel workbook) for Tableau / Power BI."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .db import Database

# file name -> (view, sort order)
EXTRACTS = {
    "schools": ("dash_schools", ["year_start", "la_name", "school_name"]),
    "local_authorities": ("dash_local_authorities", ["year_start", "rank_gap_vs_national"]),
    "beating_the_odds": ("v_beating_the_odds", ["years_beating_odds", "avg_residual_z"]),
    "national": ("v_national_trends", ["year_start"]),
}


def export(db: Database, out_dir: Path, decimals: int = 2) -> dict[str, pd.DataFrame]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = {}
    for name, (view, order) in EXTRACTS.items():
        df = db.query(f"SELECT * FROM {view}")
        ascending = name != "beating_the_odds"
        df = df.sort_values(order, ascending=ascending, na_position="last")
        df = df.round(decimals)
        df.to_csv(out_dir / f"{name}.csv", index=False)
        frames[name] = df
        print(f"  {out_dir / (name + '.csv')}: {len(df):,} rows")
    try:
        with pd.ExcelWriter(out_dir / "tutoring_gap_map.xlsx") as xl:
            for name, df in frames.items():
                df.to_excel(xl, sheet_name=name, index=False)
        print(f"  {out_dir / 'tutoring_gap_map.xlsx'}: all tables, one sheet each")
    except ImportError:
        print("  (install openpyxl to also get a single .xlsx workbook)")
    return frames
