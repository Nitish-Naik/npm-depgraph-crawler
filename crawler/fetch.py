from urllib.parse import quote

import httpx

REGISTRY_BASE = "https://registry.npmjs.org"
USER_AGENT = (
    "npm-depgraph-crawler/0.1 "
    "(research; +https://github.com/; contact: nitishnaik2022@gmail.com)"
)


def _package_url(name: str) -> str:
    # Scoped names like "@types/node" must arrive at the registry URL-encoded,
    # so the slash becomes %2F. Unscoped names are unaffected.
    return f"{REGISTRY_BASE}/{quote(name, safe='@')}"


def new_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=30.0,
        follow_redirects=True,
    )


def fetch_package(name: str, client: httpx.Client | None = None) -> dict:
    owned = client is None
    if owned:
        client = new_client()
    try:
        resp = client.get(_package_url(name))
        resp.raise_for_status()
        return resp.json()
    finally:
        if owned:
            client.close()
