import os
import tempfile

# Before anything imports app.db: tests get their own throwaway database. Without this they would use
# DATABASE_URL from the developer's .env, the same file a running backend (and a phone) is using.
_TEST_DIR = tempfile.mkdtemp(prefix="medsure_tests_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TEST_DIR, "test.db").replace("\\", "/")

import pytest  # noqa: E402

from app.config import settings  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def isolated_files(tmp_path_factory):
    """Uploads go to a temp folder, and no test reaches the real AI service."""
    settings.upload_dir = str(tmp_path_factory.mktemp("uploads"))
    settings.groq_api_key = ""
    settings.firebase_credentials = ""  # tests never send pushes, whatever the developer's .env says
    settings.demo_fallback = False
