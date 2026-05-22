import json

import httpx

from crawler import db
from crawler.store import store_package_data
from crawler.errors import classify


MAX_ATTEMPTS = 3


def _error_reason(error: BaseException) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.HTTPStatusError):
        return f"http_{error.response.status_code}"
    if isinstance(error, httpx.ConnectError):
        return "connect_error"
    if isinstance(error, httpx.NetworkError):
        return "network_error"
    if isinstance(error, json.JSONDecodeError):
        return "json_decode_error"

    reason = str(error).strip().lower().replace(" ", "_")
    return reason or error.__class__.__name__.lower()


def claim(conn):
    """Claim next package from queue, or None if empty.
    
    Atomically finds the oldest claimable row (pending OR in_progress with
    expired lease), locks it with FOR UPDATE SKIP LOCKED to prevent concurrent
    workers from claiming the same row, then marks it in_progress with a 60s
    lease. If worker crashes mid-fetch, the lease expires and another worker
    reclaims it on next run.
    
    Returns (name, attempts) tuple or None if queue empty.
    """
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
                WITH claimed AS (
                    SELECT name FROM crawl_frontier
                        WHERE state = 'pending'
                            OR (state = 'in_progress' AND claim_expires_at < now())
                        ORDER BY discovered_at
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                )

                UPDATE crawl_frontier f
                    SET state= 'in_progress',
                        claim_expires_at = now() + interval '60 seconds',
                        last_attempted_at = now(),
                        attempts = f.attempts + 1
                    FROM claimed
                WHERE f.name = claimed.name
                RETURNING f.name, f.attempts;
            """
        )

        row = cur.fetchone()

        if row:
            return (row[0], row[1]) # row as tuple

        return None

def finalize_success(conn, name, doc) -> set[str]:
    discovered = store_package_data(conn, doc)
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """UPDATE crawl_frontier 
            SET state='done', claim_expires_at=NULL, last_error=NULL
            WHERE name=%s
            """, (name, )
        )

        # INSERT discovered deps
        for dep in discovered:
            cur.execute(
                "INSERT INTO crawl_frontier (name) VALUES (%s) ON CONFLICT DO NOTHING",
                (dep, )
            )


    return discovered



def finalize_failure(conn, name, error, attempts) -> None:
    classification = classify(error)

    if classification == "retriable" and attempts < MAX_ATTEMPTS:
        new_state = 'pending'
    else:
        new_state = 'failed'
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            UPDATE crawl_frontier
            SET state = %s, claim_expires_at=NULL, last_error=%s
            WHERE name=%s
            """,
            (new_state, str(error), name)
        )

    return None



def run(max_packages=None) -> dict:
    from datetime import datetime
    from crawler.fetch import fetch_package
    import time

    stored_count = 0
    failed_count = 0
    start_time = time.time()
    last_tick = start_time

    def get_state_counts():
        """Query frontier for current state counts."""
        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT state, count(*) FROM crawl_frontier GROUP BY state")
                return dict(cur.fetchall())

    def queue_size() -> int:
        counts = get_state_counts()
        return counts.get("pending", 0)

    def print_line(event, name, **kwargs):
        """Print observability line."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name_pad = str(name).ljust(20) if name else ""
        kv = " ".join(f"{k}={v}" for k, v in kwargs.items())
        print(f"[{ts}] {event:<8} {name_pad} {kv}", flush=True)

    while True:
        # Check heartbeat
        now = time.time()
        if now - last_tick >= 30:
            counts = get_state_counts()
            print_line("tick", "", queue=counts.get("pending", 0),
                      in_progress=counts.get("in_progress", 0),
                      done=counts.get("done", 0), failed=counts.get("failed", 0))
            last_tick = now
        
        # Claim
        with db.connect() as conn:
            result = claim(conn)
        if result is None:
            # Queue drained
            break
        
        name, attempts = result
        print_line("claim", name, attempts=f"{attempts}/{MAX_ATTEMPTS}", queue=queue_size())
        
        # Fetch and route
        try:
            print_line("fetching", name, attempts=f"{attempts}/{MAX_ATTEMPTS}")
            doc = fetch_package(name)
            with db.connect() as conn:
                discovered = finalize_success(conn, name, doc)
            stored_count += 1
            print_line(
                "done",
                name,
                versions=len(doc.get("versions") or {}),
                deps_discovered=len(discovered),
                queue=queue_size(),
            )
        except Exception as e:
            with db.connect() as conn:
                finalize_failure(conn, name, e, attempts)
            failed_count += 1
            event = "retry" if classify(e) == "retriable" and attempts < MAX_ATTEMPTS else "failed"
            print_line(event, name, attempts=f"{attempts}/{MAX_ATTEMPTS}", reason=_error_reason(e), queue=queue_size())
        
        # Check max limit
        if max_packages and stored_count >= max_packages:
            break
    
    elapsed = int(time.time() - start_time)
    print_line("crawl done", "", stored=stored_count, failed=failed_count, elapsed=elapsed)
    
    return {"stored": stored_count, "failed": failed_count, "elapsed": elapsed}