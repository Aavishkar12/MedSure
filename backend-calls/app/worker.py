"""Escalation worker:  python -m app.worker

Wakes every POLL_SECONDS and processes alerts whose timer expired. You can run several copies:
rows are locked with FOR UPDATE SKIP LOCKED so no alert is processed twice.
"""
import logging
import time

from .config import settings
from .db import SessionLocal
from .escalation import run_due
from .notify import get_notifier

log = logging.getLogger("medsure.worker")


def loop(stop=lambda: False) -> None:
    log.info("escalation worker started (poll every %ss)", settings.poll_seconds)
    while not stop():
        db = SessionLocal()
        try:
            run_due(db, get_notifier())
        except Exception:
            log.exception("worker iteration failed")
            db.rollback()
        finally:
            db.close()
        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from .main import init_db

    init_db()
    loop()
