"""Drop and recreate every table. Run after a schema change: python -m app.reset_db --yes"""

import sys

from sqlmodel import SQLModel

from . import models  # noqa: F401
from .db import engine

if __name__ == "__main__":
    if "--yes" not in sys.argv:
        sys.exit(f"This deletes ALL data in {engine.url.render_as_string(hide_password=True)}. Re-run with --yes.")
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    print("Database reset.")
