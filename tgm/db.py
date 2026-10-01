"""Thin wrapper so the same pipeline writes to SQLite (default) or Postgres."""
from __future__ import annotations

import math
import re
import sqlite3
from pathlib import Path

import pandas as pd

from .config import SQL_DIR

_VIEW_RX = re.compile(r"CREATE\s+VIEW\s+(\w+)", re.IGNORECASE)


def sql_files() -> list[Path]:
    return sorted(SQL_DIR.glob("[0-9][0-9]_*.sql"))


class Database:
    def __init__(self, target: str | Path):
        target = str(target)
        if target.startswith(("postgresql://", "postgres://", "postgresql+")):
            from sqlalchemy import create_engine  # optional dependency

            self.kind = "postgres"
            self.engine = create_engine(target.replace("postgres://", "postgresql://", 1))
            self.con = self.engine
        else:
            self.kind = "sqlite"
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            self.con = sqlite3.connect(target)
            try:
                self.con.execute("SELECT sqrt(4)")
            except sqlite3.OperationalError:
                # Older SQLite builds lack math functions; the views need sqrt().
                self.con.create_function(
                    "sqrt", 1, lambda x: math.sqrt(x) if x is not None and x >= 0 else None,
                    deterministic=True,
                )
        self.label = target if self.kind == "sqlite" else re.sub(r":[^:@/]+@", ":***@", target)

    def write(self, df: pd.DataFrame, table: str) -> None:
        df.to_sql(table, self.con, if_exists="replace", index=False,
                  chunksize=5000, method="multi" if self.kind == "postgres" else None)

    def execute_script(self, sql: str) -> None:
        if self.kind == "sqlite":
            self.con.executescript(sql)
            self.con.commit()
        else:
            # Raw cursor with no parameters, so '%' in SQL comments isn't read as a placeholder.
            raw = self.engine.raw_connection()
            try:
                raw.cursor().execute(sql)
                raw.commit()
            finally:
                raw.close()

    def query(self, sql: str) -> pd.DataFrame:
        return pd.read_sql_query(sql, self.con)

    def view_names(self) -> list[str]:
        names = []
        for f in sql_files():
            names += _VIEW_RX.findall(f.read_text())
        return names

    def drop_views(self) -> None:
        """Views must go before their tables are replaced (Postgres insists)."""
        suffix = " CASCADE" if self.kind == "postgres" else ""
        self.execute_script("".join(
            f"DROP VIEW IF EXISTS {v}{suffix};\n" for v in reversed(self.view_names())
        ))

    def create_views(self) -> None:
        for f in sql_files():
            self.execute_script(f.read_text())

    def close(self) -> None:
        if self.kind == "sqlite":
            self.con.close()
        else:
            self.engine.dispose()
