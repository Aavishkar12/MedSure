from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC datetime. Every timestamp in the database is UTC and naive."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
