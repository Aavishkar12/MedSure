import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .db import Base, engine
from .routers import alerts, auth, checkins, family, twilio_hooks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def init_db() -> None:
    """create_all is fine for a hackathon. For production, move to Alembic migrations."""
    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    stop = threading.Event()
    if settings.run_worker_in_api:
        from .worker import loop

        threading.Thread(target=loop, args=(stop.is_set,), daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="MedSure API", version="0.1.0", lifespan=lifespan)
for r in (auth.router, family.router, checkins.router, alerts.router, twilio_hooks.router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"ok": True}
