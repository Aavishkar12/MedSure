"""Start the backend for a live demo, with the database in a local file.

Use this when the network blocks the hosted Postgres port (campus and event wifi often do).
Firebase sign-in and push notifications still work; they only need ordinary internet access.

    .venv/Scripts/python run_demo.py
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///./demo.db"

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
