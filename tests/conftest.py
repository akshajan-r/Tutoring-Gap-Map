import os
import sqlite3

import pandas as pd
import pytest

from tgm.load import build
from tgm.sample import generate


@pytest.fixture(scope="session")
def sample_dir(tmp_path_factory):
    return generate(tmp_path_factory.mktemp("sample"))


@pytest.fixture(scope="session")
def sqlite_db(sample_dir, tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "test.db"
    build(sample_dir, str(path)).close()
    return path


@pytest.fixture(scope="session")
def q(sqlite_db):
    con = sqlite3.connect(sqlite_db)
    yield lambda sql: pd.read_sql_query(sql, con)
    con.close()


@pytest.fixture(scope="session")
def pg_url():
    url = os.environ.get("TGM_TEST_PG_URL")
    if not url:
        pytest.skip("set TGM_TEST_PG_URL=postgresql://user:pass@host/db to run Postgres tests")
    return url
