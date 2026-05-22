from datetime import datetime
import psycopg

from crawler.store import store_package_data, store_package
from crawler.errors import classify




def claim(conn):
    """Claim next package from queue, or None if empty.
    
    Atomically finds the oldest claimable row (pending OR in_progress with
    expired lease), locks it with FOR UPDATE SKIP LOCKED to prevent concurrent
    workers from claiming the same row, then marks it in_progress with a 60s
    lease. If worker crashes mid-fetch, the lease expires and another worker
    reclaims it on next run.
    
    Returns (name, attempts) tuple or None if queue empty.
    """
    with conn.cursor() as cur:
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
    with conn.cursor() as cur:
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

    if classification == 'retriable' and attempts < 3:
        new_state = 'pending'
    else:
        new_state = 'failed'
    with conn.cursor() as cur:

        cur.execute(
            """
            UPDATE crawl_frontier
            SET state = %s, claim_expires_at=NULL, last_error=%s
            WHERE name=%s
            """,
            (new_state, str(error), name)
        )

    return None