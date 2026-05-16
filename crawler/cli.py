import argparse
import sys

from . import db, fetch, store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="depcrawler")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_one = sub.add_parser("fetch-one", help="Fetch and store a single npm package")
    p_one.add_argument("name", help="npm package name (e.g. lodash, @types/node)")

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

    return 1


if __name__ == "__main__":
    sys.exit(main())
