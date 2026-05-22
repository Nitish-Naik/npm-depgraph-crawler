from datetime import datetime, timezone, timedelta
import pytest

from crawler.loop import claim

def _row(conn, name):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, state, attempts, claim_expires_at, last_attempted_at "
            "FROM crawl_frontier WHERE name = %s", 
            (name, ),
        )

        return cur.fetchone()


def _seed_pending(conn, name):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO crawl_frontier (name) VALUES (%s)", (name, ))
    
    conn.commit()

def test_claim_returns_none_on_empty_queue(conn):
    assert claim(conn) is None

def test_claim_marks_row_in_progress_and_sets_lease(conn):
    _seed_pending(conn, "react")
    name, attempts = claim(conn)

    assert name == "react"
    assert attempts == 1
    _, state, db_attempts, lease, last_attempted = _row(conn, "react")

    assert state == "in_progress"
    assert db_attempts == 1
    assert lease is not None
    assert last_attempted is not None
    delta = lease - datetime.now(timezone.utc)
    assert timedelta(seconds=50) < delta < timedelta(seconds=70)

def test_claim_skips_in_progress_with_valid_lease(conn):
    _seed_pending(conn, "react")
    _seed_pending(conn, "lodash")
    # First claim: react
    claim(conn)
    # Second claim: should get lodash, not react (react's lease is still valid).
    name, attempts = claim(conn)
    assert name == "lodash"
    assert attempts == 1


def test_claim_recaptures_in_progress_with_expired_lease(conn):
    _seed_pending(conn, "react")
    # First claim sets a valid lease.
    claim(conn)
    # Force the lease into the past.
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE crawl_frontier SET claim_expires_at = now() - interval '1 minute' "
            "WHERE name = 'react'"
        )
    conn.commit()
    # Second claim should pick it back up.
    name, attempts = claim(conn)
    assert name == "react"
    assert attempts == 2  # claim bumped attempts from 1 to 2