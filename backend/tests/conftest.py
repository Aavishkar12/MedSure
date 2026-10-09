import pytest

from app.config import settings


@pytest.fixture(scope="session", autouse=True)
def isolated_files(tmp_path_factory):
    """Uploads and extraction JSON go to a temp folder, and no test reaches the real AI service."""
    settings.extractions_dir = str(tmp_path_factory.mktemp("extractions"))
    settings.upload_dir = str(tmp_path_factory.mktemp("uploads"))
    settings.groq_api_key = ""
    settings.demo_fallback = False
