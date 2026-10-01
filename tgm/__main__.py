"""Command line: python -m tgm <command> [options]

  download   fetch the raw files (best effort; prints manual steps if blocked)
  build      clean + join the raw files, load the database, create SQL views
  export     write dashboard CSVs / xlsx from the database
  dashboard  write a self-contained HTML preview of the dashboard
  all        build + export + dashboard

Add --sample to run everything on generated synthetic data instead.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import config


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m tgm", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["download", "build", "export", "dashboard", "all"])
    ap.add_argument("--sample", action="store_true",
                    help="generate and use SYNTHETIC data (no downloads needed)")
    ap.add_argument("--raw-dir", type=Path, default=None, help=f"default: {config.RAW_DIR}")
    ap.add_argument("--db", default=None,
                    help="SQLite path or postgresql://user:pass@host/db (default: data/tutoring_gap.db)")
    ap.add_argument("--out", type=Path, default=config.OUTPUT_DIR, help="output folder")
    ap.add_argument("--years", nargs="*", default=config.KS4_YEARS, help="academic years to download")
    args = ap.parse_args(argv)

    raw_dir = args.raw_dir or (config.SAMPLE_DIR if args.sample else config.RAW_DIR)
    db_target = args.db or str(config.DEFAULT_DB.with_name(
        "tutoring_gap_sample.db" if args.sample else config.DEFAULT_DB.name))

    if args.command == "download":
        if args.sample:
            raise SystemExit("--sample doesn't download anything; run `build --sample`.")
        from .download import download_all
        download_all(raw_dir, args.years)
        return

    if args.sample and args.command in ("build", "all"):
        from .sample import generate
        print(f"Generating SYNTHETIC sample data in {raw_dir}")
        generate(raw_dir)

    from .db import Database
    if args.command in ("build", "all"):
        from .load import build
        db = build(raw_dir, db_target)
    else:
        db = Database(db_target)

    if args.command in ("export", "all"):
        from .export import export
        print("Exporting dashboard tables")
        export(db, args.out / "dashboard_data")
    if args.command in ("dashboard", "all"):
        from .dashboard import write_dashboard
        path = write_dashboard(db, args.out / "tutoring_gap_map.html", synthetic=args.sample)
        print(f"  HTML preview: {path}")
    db.close()


if __name__ == "__main__":
    main()
