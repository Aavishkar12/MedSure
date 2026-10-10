from app.db import normalize_database_url


def test_normalizes_neon_psycopg_url_to_installed_driver():
    raw = "postgresql+psycopg://user:password@host.example/db?sslmode=require"
    assert normalize_database_url(raw) == (
        "postgresql+psycopg2://user:password@host.example/db?sslmode=require"
    )


def test_normalizes_legacy_postgres_scheme():
    assert normalize_database_url("postgres://user:password@host/db") == (
        "postgresql://user:password@host/db"
    )


def test_keeps_standard_postgresql_and_sqlite_urls():
    assert normalize_database_url("postgresql://user:password@host/db") == (
        "postgresql://user:password@host/db"
    )
    assert normalize_database_url("sqlite:///./medsure.db") == "sqlite:///./medsure.db"
