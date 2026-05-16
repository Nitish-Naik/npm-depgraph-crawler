-- npm-depgraph-crawler schema
--
-- Five tables:
--   packages          one row per npm package (name)
--   package_versions  one row per published (name, version)
--   dependencies      one edge per (dependent name+version, dependency name, type)
--   raw_documents     full registry JSON, kept so re-parsing never requires re-fetching
--   crawl_frontier    the work queue; state machine drives BFS over the dep graph

BEGIN;

CREATE TABLE IF NOT EXISTS packages (
    name                TEXT PRIMARY KEY,
    description         TEXT,
    homepage            TEXT,
    license             TEXT,
    repository_url      TEXT,
    latest_version      TEXT,
    first_published_at  TIMESTAMPTZ,
    last_published_at   TIMESTAMPTZ,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS package_versions (
    name          TEXT NOT NULL REFERENCES packages(name) ON DELETE CASCADE,
    version       TEXT NOT NULL,
    published_at  TIMESTAMPTZ,
    deprecated    TEXT,
    PRIMARY KEY (name, version)
);

DO $$ BEGIN
    CREATE TYPE dep_type AS ENUM ('runtime', 'dev', 'peer', 'optional');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS dependencies (
    dependent_name     TEXT NOT NULL,
    dependent_version  TEXT NOT NULL,
    dependency_name    TEXT NOT NULL,
    dependency_range   TEXT NOT NULL,
    dep_type           dep_type NOT NULL,
    PRIMARY KEY (dependent_name, dependent_version, dependency_name, dep_type),
    FOREIGN KEY (dependent_name, dependent_version)
        REFERENCES package_versions(name, version) ON DELETE CASCADE
);

-- Reverse-lookup index: "who depends on X?" is the central question of the project,
-- and without this index it's a sequential scan of millions of rows.
CREATE INDEX IF NOT EXISTS dependencies_by_target
    ON dependencies (dependency_name);

CREATE TABLE IF NOT EXISTS raw_documents (
    name        TEXT PRIMARY KEY REFERENCES packages(name) ON DELETE CASCADE,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    etag        TEXT,
    document    JSONB NOT NULL
);

DO $$ BEGIN
    CREATE TYPE crawl_state AS ENUM ('pending', 'in_progress', 'done', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS crawl_frontier (
    name               TEXT PRIMARY KEY,
    state              crawl_state NOT NULL DEFAULT 'pending',
    attempts           INT NOT NULL DEFAULT 0,
    last_attempted_at  TIMESTAMPTZ,
    last_error         TEXT,
    discovered_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Partial index makes SELECT ... FOR UPDATE SKIP LOCKED on pending rows cheap
-- regardless of how many done/failed rows accumulate over the crawl.
CREATE INDEX IF NOT EXISTS crawl_frontier_pending
    ON crawl_frontier (discovered_at)
    WHERE state = 'pending';

COMMIT;
