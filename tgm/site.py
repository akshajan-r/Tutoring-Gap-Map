"""A static website for GitHub Pages: the dashboard as index.html plus the data as downloads."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .dashboard import write_dashboard
from .db import Database
from .export import export


def _repo_url() -> str | None:
    # Set automatically inside GitHub Actions.
    repo = os.environ.get("GITHUB_REPOSITORY")
    return f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}" if repo else None


def build_site(db: Database, site_dir: Path, synthetic: bool = False) -> Path:
    if site_dir.exists():
        shutil.rmtree(site_dir)
    data_dir = site_dir / "data"
    frames = export(db, data_dir)
    downloads = [(f"{name.replace('_', ' ').capitalize()} (CSV)", f"data/{name}.csv") for name in frames]
    if (data_dir / "tutoring_gap_map.xlsx").exists():
        downloads.append(("Everything (Excel)", "data/tutoring_gap_map.xlsx"))
    index = write_dashboard(db, site_dir / "index.html", synthetic=synthetic,
                            downloads=downloads, repo_url=_repo_url())
    print(f"  {index}")
    return index
