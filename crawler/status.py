from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Connection(Protocol):
    def cursor(self): ...


@dataclass(frozen=True)
class CrawlStatus:
    frontier: dict[str, int]
    packages: int
    versions: int
    dependencies: int
    recent_failures: list[tuple[str, int]]


def get_status(conn: Connection, *, failure_limit: int = 10) -> CrawlStatus:
    """Read a compact operational snapshot of the crawl database."""
    with conn.cursor() as cur:
        cur.execute("SELECT state, count(*) FROM crawl_frontier GROUP BY state")
        frontier = {state: count for state, count in cur.fetchall()}

        cur.execute("SELECT count(*) FROM packages")
        packages = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM package_versions")
        versions = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM dependencies")
        dependencies = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COALESCE(last_error, '<unknown>') AS reason, count(*)
            FROM crawl_frontier
            WHERE state = 'failed'
            GROUP BY reason
            ORDER BY count(*) DESC, reason
            LIMIT %s
            """,
            (failure_limit,),
        )
        recent_failures = [(reason, count) for reason, count in cur.fetchall()]

    return CrawlStatus(
        frontier=frontier,
        packages=packages,
        versions=versions,
        dependencies=dependencies,
        recent_failures=recent_failures,
    )


def format_status(status: CrawlStatus) -> str:
    pending = status.frontier.get("pending", 0)
    in_progress = status.frontier.get("in_progress", 0)
    done = status.frontier.get("done", 0)
    failed = status.frontier.get("failed", 0)

    lines = [
        "crawl status",
        f"frontier: pending={pending} in_progress={in_progress} done={done} failed={failed}",
        f"stored: packages={status.packages} versions={status.versions} dependencies={status.dependencies}",
    ]

    if status.recent_failures:
        lines.append("failure reasons:")
        for reason, count in status.recent_failures:
            lines.append(f"  {count}x {reason}")
    else:
        lines.append("failure reasons: none")

    return "\n".join(lines)
