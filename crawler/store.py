from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

DEP_FIELDS: dict[str, str] = {
    "dependencies": "runtime",
    "devDependencies": "dev",
    "peerDependencies": "peer",
    "optionalDependencies": "optional",
}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_license(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        t = value.get("type")
        return t if isinstance(t, str) else None
    return None


def _normalize_repository(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        url = value.get("url")
        return url if isinstance(url, str) else None
    return None


def _normalize_homepage(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def store_package(conn: psycopg.Connection, doc: dict) -> set[str]:
    """Persist one registry document and return newly discovered dependency names."""
    name = doc.get("name")
    if not isinstance(name, str):
        raise ValueError("registry document is missing a string 'name' field")

    times: dict = doc.get("time") or {}
    versions: dict = doc.get("versions") or {}
    dist_tags: dict = doc.get("dist-tags") or {}
    latest = dist_tags.get("latest") if isinstance(dist_tags, dict) else None

    discovered: set[str] = set()

    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO packages (
                name, description, homepage, license, repository_url,
                latest_version, first_published_at, last_published_at, fetched_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (name) DO UPDATE SET
                description        = EXCLUDED.description,
                homepage           = EXCLUDED.homepage,
                license            = EXCLUDED.license,
                repository_url     = EXCLUDED.repository_url,
                latest_version     = EXCLUDED.latest_version,
                first_published_at = EXCLUDED.first_published_at,
                last_published_at  = EXCLUDED.last_published_at,
                fetched_at         = now()
            """,
            (
                name,
                doc.get("description") if isinstance(doc.get("description"), str) else None,
                _normalize_homepage(doc.get("homepage")),
                _normalize_license(doc.get("license")),
                _normalize_repository(doc.get("repository")),
                latest if isinstance(latest, str) else None,
                _parse_ts(times.get("created")) if isinstance(times, dict) else None,
                _parse_ts(times.get("modified")) if isinstance(times, dict) else None,
            ),
        )

        cur.execute(
            """
            INSERT INTO raw_documents (name, document, fetched_at)
            VALUES (%s, %s, now())
            ON CONFLICT (name) DO UPDATE SET
                document   = EXCLUDED.document,
                fetched_at = now()
            """,
            (name, Jsonb(doc)),
        )

        for version, vdoc in versions.items():
            if not isinstance(version, str) or not isinstance(vdoc, dict):
                continue

            cur.execute(
                """
                INSERT INTO package_versions (name, version, published_at, deprecated)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (name, version) DO UPDATE SET
                    published_at = EXCLUDED.published_at,
                    deprecated   = EXCLUDED.deprecated
                """,
                (
                    name,
                    version,
                    _parse_ts(times.get(version)) if isinstance(times, dict) else None,
                    vdoc.get("deprecated") if isinstance(vdoc.get("deprecated"), str) else None,
                ),
            )

            for field, dep_type in DEP_FIELDS.items():
                deps = vdoc.get(field)
                if not isinstance(deps, dict):
                    continue
                for dep_name, dep_range in deps.items():
                    if not isinstance(dep_name, str) or not isinstance(dep_range, str):
                        continue
                    cur.execute(
                        """
                        INSERT INTO dependencies (
                            dependent_name, dependent_version,
                            dependency_name, dependency_range, dep_type
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (dependent_name, dependent_version,
                                     dependency_name, dep_type)
                        DO UPDATE SET dependency_range = EXCLUDED.dependency_range
                        """,
                        (name, version, dep_name, dep_range, dep_type),
                    )
                    discovered.add(dep_name)

        cur.execute(
            """
            INSERT INTO crawl_frontier (name, state, last_attempted_at, attempts)
            VALUES (%s, 'done', now(), 1)
            ON CONFLICT (name) DO UPDATE SET
                state             = 'done',
                last_attempted_at = now(),
                attempts          = crawl_frontier.attempts + 1,
                last_error        = NULL
            """,
            (name,),
        )

        for dep_name in discovered:
            cur.execute(
                "INSERT INTO crawl_frontier (name) VALUES (%s) ON CONFLICT DO NOTHING",
                (dep_name,),
            )

    return discovered
