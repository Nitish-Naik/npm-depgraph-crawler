import argparse
import sys

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional runtime convenience
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

from . import db, fetch, loop, seed, status, store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="depcrawler")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_one = sub.add_parser("fetch-one", help="Fetch and store a single npm package")
    p_one.add_argument("name", help="npm package name (e.g. lodash, @types/node)")

    p_seed = sub.add_parser("seed", help="Seed the crawl frontier")
    p_seed.add_argument(
        "--from-file",
        dest="from_file",
        help="Read package names from a newline-separated file",
    )

    p_crawl = sub.add_parser("crawl", help="Run the resumable crawl loop")
    p_crawl.add_argument(
        "--max-packages",
        type=int,
        default=None,
        help="Stop after this many successful stores",
    )
    p_crawl.add_argument(
        "--max-seconds",
        type=int,
        default=None,
        help="Stop after roughly this many seconds",
    )
    p_crawl.add_argument(
        "--requests-per-second",
        type=float,
        default=loop.DEFAULT_REQUESTS_PER_SECOND,
        help="Client-side npm registry request rate; use 0 to disable throttling",
    )
    p_crawl.add_argument(
        "--retry-after-max-seconds",
        type=float,
        default=loop.DEFAULT_RETRY_AFTER_MAX_SECONDS,
        help="Maximum seconds to sleep when honoring a Retry-After header",
    )

    sub.add_parser("status", help="Show crawl progress and recent failure reasons")

    args = parser.parse_args(argv)

    if args.cmd == "fetch-one":
        doc = fetch.fetch_package(args.name)
        with db.connect() as conn:
            discovered = store.store_package(conn, doc)
        n_versions = len(doc.get("versions") or {})
        print(
            f"stored {args.name}: {n_versions} versions, "
            f"{len(discovered)} unique dependency names discovered"
        )
        return 0

    if args.cmd == "seed":
        with db.connect() as conn:
            if args.from_file:
                inserted = seed.seed_from_file(conn, args.from_file)
            else:
                inserted = seed.seed_default(conn)
        print(f"seeded {inserted} packages")
        return 0

    if args.cmd == "crawl":
        summary = loop.run(
            max_packages=args.max_packages,
            max_seconds=args.max_seconds,
            requests_per_second=args.requests_per_second,
            retry_after_max_seconds=args.retry_after_max_seconds,
        )
        print(
            f"crawl done: stored={summary['stored']} "
            f"failed={summary['failed']} elapsed={summary['elapsed']}s "
            f"reason={summary['reason']}"
        )
        return 0

    if args.cmd == "status":
        with db.connect() as conn:
            snapshot = status.get_status(conn)
        print(status.format_status(snapshot))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
