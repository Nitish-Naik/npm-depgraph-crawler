from pathlib import Path

import psycopg

DEFAULT_SEEDS: list[str] = [
    "react",
    "vue",
    "angular",
    "svelte",
    "next",
    "nuxt",
    "express",
    "koa",
    "fastify",
    "nestjs",
    "lodash",
    "ramda",
    "axios",
    "webpack",
    "vite",
    "rollup",
    "esbuild",
    "typescript",
    "eslint",
    "prettier",
    "jest",
    "mocha",
    "vitest",
    "chalk",
    "commander",
]


def _insert_names(conn: psycopg.Connection, names: list[str]) -> int:
    if not names:
        return 0
    inserted = 0
    with conn.transaction(), conn.cursor() as cur:
        for name in names:
            cur.execute(
                "INSERT INTO crawl_frontier (name) VALUES (%s) "
                "ON CONFLICT DO NOTHING RETURNING name",
                (name,),
            )
            if cur.fetchone() is not None:
                inserted += 1
    return inserted


def seed_default(conn: psycopg.Connection) -> int:
    """Seed the frontier with DEFAULT_SEEDS. Returns number of new rows."""
    return _insert_names(conn, DEFAULT_SEEDS)


def seed_from_file(conn: psycopg.Connection, path: str) -> int:
    """Seed from a newline-separated file. Blank lines and lines starting
    with `#` are ignored. Whitespace is stripped. Returns number of new rows.
    """
    raw = Path(path).read_text(encoding="utf-8")
    names: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        names.append(stripped)
    return _insert_names(conn, names)