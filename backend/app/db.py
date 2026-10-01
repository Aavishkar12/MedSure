from sqlmodel import Session, SQLModel, create_engine

from .config import settings

url = settings.database_url
if url.startswith("postgres://"):  # some hosts hand out the old scheme
    url = "postgresql://" + url[len("postgres://"):]

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
