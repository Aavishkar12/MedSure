import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[1]
HEAD = "e7725f800001"
BASELINE = "054953239378"
EXPECTED_TABLES = {
    "alembic_version",
    "billitem",
    "case",
    "casemember",
    "casestate",
    "checkin",
    "checklistitem",
    "claim",
    "device",
    "dischargecard",
    "document",
    "draft",
    "invite",
    "processingjob",
    "timelineevent",
    "user",
}


def run_module(module: str, *args: str, database_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def revision_and_tables(database_url: str) -> tuple[str, set[str]]:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    return revision, tables


def test_fresh_database_upgrades_to_head(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    run_module("app.migrate", database_url=database_url)

    revision, tables = revision_and_tables(database_url)
    assert revision == HEAD
    assert tables == EXPECTED_TABLES


def test_existing_pre_alembic_database_is_adopted_and_upgraded(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    run_module("alembic", "upgrade", BASELINE, database_url=database_url)

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
    engine.dispose()

    run_module("app.migrate", database_url=database_url)
    revision, tables = revision_and_tables(database_url)
    assert revision == HEAD
    assert "casestate" in tables
