"""Empty the demo database (the local file run_demo.py uses) so the next demo starts fresh.

    .venv/Scripts/python reset_demo.py --yes

Log out on every phone first. The server can stay running. This never touches the hosted database.
"""

import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./demo.db"  # same file as run_demo.py

from sqlmodel import SQLModel  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import engine  # noqa: E402

if __name__ == "__main__":
    if "--yes" not in sys.argv:
        sys.exit("This deletes every user, case and check-in in demo.db. Re-run with --yes.")
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    print("Demo database is empty. Sign in again on the phones to start a fresh demo.")
