from sqlmodel import Session, SQLModel, create_engine

from .config import settings

def normalize_database_url(raw_url: str) -> str:
    """Use the installed psycopg2 driver for common hosted Postgres URL forms."""
    if raw_url.startswith("postgres://"):  # some hosts hand out the old scheme
        return "postgresql://" + raw_url[len("postgres://"):]
    if raw_url.startswith("postgresql+psycopg://"):  # Neon SQLAlchemy preset uses psycopg v3
        return "postgresql+psycopg2://" + raw_url[len("postgresql+psycopg://"):]
    return raw_url


url = normalize_database_url(settings.database_url)

# connect_timeout: fail in seconds, not minutes, on networks that block the Postgres port.
connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {"connect_timeout": 10}
# pool_pre_ping: hosted Postgres drops idle connections.
engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)


def init_db() -> None:
    from . import models  # noqa: F401  (registers tables)

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
