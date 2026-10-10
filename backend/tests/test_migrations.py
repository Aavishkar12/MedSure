import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlmodel import SQLModel

from app import models  # noqa: F401 - registers metadata


ROOT = Path(__file__).resolve().parents[1]
HEAD = "b93a4d200001"
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
    "coveragereport",
    "device",
    "dischargecard",
    "document",
    "draft",
    "invite",
    "policysummary",
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


def test_fresh_database_upgrades_to_current_main_schema(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    run_module("app.migrate", database_url=database_url)

    revision, tables = revision_and_tables(database_url)
    assert revision == HEAD
    assert tables == EXPECTED_TABLES
    columns = {c["name"] for c in inspect(create_engine(database_url)).get_columns("document")}
    assert {"classified_type", "extraction_method", "extraction"} <= columns


def test_existing_pre_alembic_database_is_adopted_without_data_loss(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    run_module("alembic", "upgrade", BASELINE, database_url=database_url)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO user (id, name) VALUES ('legacy-user', 'Lakshmi')"))
        connection.execute(text("DROP TABLE alembic_version"))
    engine.dispose()

    run_module("app.migrate", database_url=database_url)
    revision, tables = revision_and_tables(database_url)
    assert revision == HEAD
    assert tables == EXPECTED_TABLES
    with create_engine(database_url).connect() as connection:
        assert connection.execute(text("SELECT name FROM user WHERE id='legacy-user'")).scalar_one() == "Lakshmi"


def test_unmanaged_latest_app_schema_is_adopted(tmp_path: Path):
    """Covers databases previously created by SQLModel.create_all on main."""
    database_url = f"sqlite:///{(tmp_path / 'latest-legacy.db').as_posix()}"
    legacy_engine = create_engine(database_url)
    SQLModel.metadata.create_all(legacy_engine)
    legacy_engine.dispose()

    run_module("app.migrate", database_url=database_url)
    revision, tables = revision_and_tables(database_url)
    assert revision == HEAD
    assert tables == EXPECTED_TABLES
