"""Apply database migrations without deleting existing data.

Existing MedSure databases predate Alembic. The first run validates their
tables and columns, stamps the matching baseline, and then applies newer
migrations. Fresh databases are created entirely through Alembic.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from . import models  # noqa: F401  (register SQLModel metadata)
from .db import engine
from .models import SQLModel

BASELINE_REVISION = "054953239378"
SHARED_STATE_REVISION = "728a18300001"
HEAD_REVISION = "e7725f800001"


def _config() -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False).replace("%", "%%"))
    return config


def _validate_legacy_schema(table_names: set[str]) -> None:
    """Refuse to stamp a partial or stale legacy schema as migration-ready."""
    expected = {table.name: set(table.columns.keys()) for table in SQLModel.metadata.sorted_tables}
    baseline_expected = {
        name: columns
        for name, columns in expected.items()
        if name not in {"casestate", "processingjob"}
    }
    baseline_expected["document"] -= {"classified_type", "extraction_method", "extraction"}
    missing_tables = sorted(set(baseline_expected) - table_names)
    if missing_tables:
        raise RuntimeError(
            "Legacy database is incomplete; missing tables: " + ", ".join(missing_tables)
        )

    db_inspector = inspect(engine)
    missing_columns: list[str] = []
    for table_name, columns in baseline_expected.items():
        actual = {column["name"] for column in db_inspector.get_columns(table_name)}
        missing_columns.extend(f"{table_name}.{name}" for name in sorted(columns - actual))
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
        document_columns = {column["name"] for column in inspect(engine).get_columns("document")}
        has_processing_schema = "processingjob" in table_names and {
            "classified_type", "extraction_method", "extraction"
        }.issubset(document_columns)
        if has_processing_schema:
            legacy_revision = HEAD_REVISION
        elif "casestate" in table_names:
            legacy_revision = SHARED_STATE_REVISION
        else:
            legacy_revision = BASELINE_REVISION
        command.stamp(config, legacy_revision)
    command.upgrade(config, "head")


if __name__ == "__main__":
    upgrade_database()
    print(f"Database is at migration {HEAD_REVISION}.")
