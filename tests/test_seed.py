from pathlib import Path

import pytest

from crawler.seed import DEFAULT_SEEDS, seed_default, seed_from_file

def _pending_names(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM crawl_frontier WHERE state= 'pending'")
        return {row[0] for row in cur.fetchall()}


def test_default_seeds_is_a_nontrivial_list():
    assert isinstance(DEFAULT_SEEDS, list)
    assert len(DEFAULT_SEEDS) >= 20
    assert all(isinstance(n, str) and n for n in DEFAULT_SEEDS)
    assert len(set(DEFAULT_SEEDS)) == len(DEFAULT_SEEDS), "duplicates in DEFAULT_SEEDS"

    

def test_seed_default_inserts_all(conn):
    inserted = seed_default(conn)
    assert inserted == len(DEFAULT_SEEDS)
    assert _pending_names(conn) == set(DEFAULT_SEEDS)

def test_seed_default_is_idempotent(conn):
    first = seed_default(conn)
    second = seed_default(conn)
    assert first == len(DEFAULT_SEEDS)
    assert second == 0



def test_seed_from_file_handles_comments_and_blanks(conn, tmp_path: Path):
    f = tmp_path / "seeds.txt"
    f.write_text(
        "react\n"
        "# this is a comment\n"
        "\n"
        "lodash\n"
        "   express   \n"
        "# another comment\n"
    )
    inserted = seed_from_file(conn, str(f))
    assert inserted == 3
    assert _pending_names(conn) == {"react", "lodash", "express"}


def test_seed_from_file_idempotent_on_overlap(conn, tmp_path: Path):
    f = tmp_path / "seeds.txt"
    f.write_text("react\nlodash\n")
    assert seed_from_file(conn, str(f)) == 2
    assert seed_from_file(conn, str(f)) == 0