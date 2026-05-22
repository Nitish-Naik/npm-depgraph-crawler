import os

from dotenv import load_dotenv
load_dotenv()
import psycopg
import pytest

TEST_DSN = os.environ.get("TEST_DATABASE_URL")

ALL_TABLES = (
    "dependencies",
    "package_versions",
    "raw_documents",
    "packages",
    "crawl_frontier",
)


@pytest.fixture
def conn():
    """Yeild a connection to a freshly-truncated test database."""
    if not TEST_DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    
    with psycopg.connect(TEST_DSN) as c:
        with c.cursor() as cur:
            cur.execute(
                "TRUNCATE " + ", ".join(ALL_TABLES) + " RESTART IDENTITY CASCADE"
            )
        c.commit()
        yield c