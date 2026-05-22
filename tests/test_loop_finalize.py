import pytest
import httpx
from unittest.mock import Mock
from crawler.loop import finalize_success, finalize_failure
from crawler.errors import classify


def _row(conn, name):
    """Fetch a single row from crawl_frontier by name."""
    with conn.cursor() as cur:
        cur.execute("SELECT state, attempts, last_error, claim_expires_at FROM crawl_frontier WHERE name=%s", (name,))
        return cur.fetchone()


def _seed_in_progress(conn, name, attempts=1):
    """Seed a row in in_progress state with a live lease."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO crawl_frontier (name, state, attempts, claim_expires_at, last_attempted_at)
               VALUES (%s, 'in_progress', %s, now() + interval '60 seconds', now())""",
            (name, attempts)
        )


def _canned_doc(name="test-pkg", versions=2, deps=None):
    """Return a minimal registry doc for testing."""
    if deps is None:
        deps = ["dep1", "dep2"]
    # Each version doc has dependencies field (dict of dep_name -> range_spec)
    return {
        "name": name,
        "versions": {
            f"1.0.{i}": {
                "dependencies": {dep: "*" for dep in deps}
            }
            for i in range(versions)
        },
    }


class TestFinalizeSuccess:
    def test_finalize_success_transitions_to_done(self, conn):
        """Row transitions to done, lease cleared, error cleared."""
        _seed_in_progress(conn, "react", attempts=1)
        doc = _canned_doc("react", deps=["lodash", "redux"])

        discovered = finalize_success(conn, "react", doc)

        state, attempts, error, lease = _row(conn, "react")
        assert state == "done"
        assert lease is None  # Lease cleared
        assert error is None  # Error cleared
        assert attempts == 1  # Unchanged
        assert discovered == {"lodash", "redux"}

    def test_finalize_success_seeds_discovered_deps(self, conn):
        """Discovered dependencies are inserted into frontier."""
        _seed_in_progress(conn, "react", attempts=1)
        doc = _canned_doc("react", deps=["lodash", "redux"])

        finalize_success(conn, "react", doc)

        with conn.cursor() as cur:
            cur.execute("SELECT name FROM crawl_frontier WHERE state='pending' ORDER BY name")
            pending_names = [row[0] for row in cur.fetchall()]

        assert "lodash" in pending_names
        assert "redux" in pending_names

    def test_finalize_success_idempotent_on_deps(self, conn):
        """Re-seeding same deps is a no-op (ON CONFLICT DO NOTHING)."""
        _seed_in_progress(conn, "react", attempts=1)
        doc = _canned_doc("react", deps=["lodash"])

        finalize_success(conn, "react", doc)
        finalize_success(conn, "react", doc)  # Call again

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM crawl_frontier WHERE name='lodash'")
            count = cur.fetchone()[0]

        assert count == 1  # Only one lodash row


class TestFinalizeFailure:
    def test_finalize_failure_retriable_attempts_under_max(self, conn):
        """Retriable error + attempts < 3 -> state='pending'."""
        _seed_in_progress(conn, "react", attempts=1)
        error = httpx.TimeoutException("timeout")

        finalize_failure(conn, "react", error, attempts=1)

        state, attempts, err_msg, lease = _row(conn, "react")
        assert state == "pending"
        assert lease is None  # Lease cleared
        assert "timeout" in err_msg

    def test_finalize_failure_retriable_exhausts_attempts(self, conn):
        """Retriable error + attempts >= 3 -> state='failed'."""
        _seed_in_progress(conn, "react", attempts=3)
        error = httpx.TimeoutException("timeout")

        finalize_failure(conn, "react", error, attempts=3)

        state, attempts, err_msg, lease = _row(conn, "react")
        assert state == "failed"
        assert lease is None  # Lease cleared
        assert "timeout" in err_msg

    def test_finalize_failure_fatal_error_always_fails(self, conn):
        """Fatal error -> state='failed' regardless of attempts."""
        _seed_in_progress(conn, "react", attempts=1)
        # Create a mock response with 404 status
        mock_response = Mock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("404 Not Found", request=Mock(), response=mock_response)

        finalize_failure(conn, "react", error, attempts=1)

        state, attempts, err_msg, lease = _row(conn, "react")
        assert state == "failed"
        assert lease is None

    def test_finalize_failure_fatal_json_decode_error(self, conn):
        """JSONDecodeError is fatal -> state='failed'."""
        import json
        _seed_in_progress(conn, "react", attempts=1)
        error = json.JSONDecodeError("Expecting value", "invalid", 0)

        finalize_failure(conn, "react", error, attempts=1)

        state, attempts, err_msg, lease = _row(conn, "react")
        assert state == "failed"
        assert lease is None
