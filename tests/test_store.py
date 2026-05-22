from crawler.store import store_package, store_package_data

CANNED_DOC = {
    "name": "tiny-test-pkg",
    "description": "fixture",
    "dist-tags": {"latest": "1.0.0"},
    "time": {"created": "2024-01-01T00:00:00.000Z", "modified": "2024-01-02T00:00:00.000Z", "1.0.0": "2024-01-01T00:00:00.000Z"},
    "versions": {
        "1.0.0": {
            "dependencies": {"dep-a": "^1.0.0", "dep-b": "^2.0.0"},
        },
    },
}

def _frontier_row(conn, name):
    with conn.cursor() as cur:
        cur.execute("SELECT name, state, attempts FROM crawl_frontier WHERE name = %s", (name, ))
        
        return cur.fetchone()


def test_store_package_data_does_not_touch_frontier(conn):
    discovered = store_package_data(conn, CANNED_DOC)
    assert discovered == {"dep-a", "dep-b"}
    # The package's own frontier row must NOT have been written by store_package_data.
    assert _frontier_row(conn, "tiny-test-pkg") is None
    # Discovered deps must also NOT have been seeded by store_package_data.
    assert _frontier_row(conn, "dep-a") is None


def test_store_package_preserves_legacy_behavior(conn):
    discovered = store_package(conn, CANNED_DOC)
    assert discovered == {"dep-a", "dep-b"}
    name, state, attempts = _frontier_row(conn, "tiny-test-pkg")
    assert (name, state, attempts) == ("tiny-test-pkg", "done", 1)
    # Discovered deps are seeded as pending.
    name, state, attempts = _frontier_row(conn, "dep-a")
    assert state == "pending"