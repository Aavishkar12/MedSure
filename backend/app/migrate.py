"""Apply Alembic migrations without deleting existing MedSure data.

Older checkouts used SQLModel.create_all and therefore have no Alembic marker.
We validate that legacy schema, stamp the newest revision it safely matches, and
then apply the remaining changes. A partial/unknown database is never stamped.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from . import models  # noqa: F401 - registers SQLModel metadata
from .db import engine
from .models import SQLModel

BASELINE_REVISION = "054953239378"
SHARED_STATE_REVISION = "728a18300001"
PROCESSING_REVISION = "e7725f800001"
HEAD_REVISION = "b93a4d200001"


def _config() -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option(
        "sqlalchemy.url", engine.url.render_as_string(hide_password=False).replace("%", "%%")
    )
    return config


def _validate_legacy_schema(table_names: set[str]) -> None:
    """Require the complete original schema before adopting an unmanaged DB."""
    expected = {table.name: set(table.columns.keys()) for table in SQLModel.metadata.sorted_tables}
    newer_tables = {"casestate", "processingjob", "policysummary", "coveragereport"}
    baseline_expected = {
        name: columns for name, columns in expected.items() if name not in newer_tables
    }
    baseline_expected["document"] -= {
        "classified_type", "extraction_method", "extraction"
    }
    missing_tables = sorted(set(baseline_expected) - table_names)
    if missing_tables:
        raise RuntimeError(
            "Legacy database is incomplete; missing tables: " + ", ".join(missing_tables)
        )

    db_inspector = inspect(engine)
    missing_columns: list[str] = []
    for table_name, columns in baseline_expected.items():
        actual = {column["name"] for column in db_inspector.get_columns(table_name)}
        missing_columns.extend(
            f"{table_name}.{name}" for name in sorted(columns - actual)
        )
    if missing_columns:
        raise RuntimeError(
            "Legacy database is incomplete; missing columns: " + ", ".join(missing_columns)
        )


def upgrade_database() -> None:
    config = _config()
    table_names = set(inspect(engine).get_table_names())
    if not table_names:
        command.upgrade(config, "head")
        return

    if "alembic_version" not in table_names:
        _validate_legacy_schema(table_names)
        document_columns = {
            column["name"] for column in inspect(engine).get_columns("document")
        }
        has_extraction = {
            "classified_type", "extraction_method", "extraction"
        }.issubset(document_columns)
        if has_extraction and "processingjob" in table_names:
            legacy_revision = PROCESSING_REVISION
        elif "casestate" in table_names:
            legacy_revision = SHARED_STATE_REVISION
        else:
            legacy_revision = BASELINE_REVISION
        command.stamp(config, legacy_revision)
    command.upgrade(config, "head")


if __name__ == "__main__":
    upgrade_database()
    print(f"Database is at migration {HEAD_REVISION}.")
