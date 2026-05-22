
# npm Dependency Graph Crawler

A resumable crawler that walks the npm package registry and its dependency graph, with its performance-critical path in Rust, and answers a question I got curious about: **how deep does the npm dependency graph actually go, and which packages are the load-bearing nodes that most of the ecosystem silently depends on?**

## What this is

npm has over three million packages wired together by tens of millions of dependency edges. This project seeds a crawler with a set of popular packages, fetches each one's registry metadata, follows its dependency edges to new packages, and keeps going — a breadth-first traversal over a graph, which is structurally the same problem as crawling the web.

The crawl runs on a single machine, but the work queue lives in PostgreSQL and is designed so it could be shared across many workers. The output is a dataset of the whole registry that I can actually query to answer the depth question above.

## Why I'm building it

I wanted a project that was a real systems problem rather than a CRUD app — something where scale creates genuine problems and I have to deal with them. A registry-wide crawl does that: at three million packages, naive approaches stop working, and I have to think about resumability, politeness, throughput, and query planning for real.

I'm also using it to push into territory that's new for me. The crawler starts in Python, where I'm comfortable, but the fetch-and-parse hot path gets rewritten in Rust once I can measure why it needs to be — so the Rust isn't decoration, it's a response to a profiled bottleneck.

## Architecture

- **Python** owns orchestration — the crawl loop, the frontier, all database work.
- **Rust** (a PyO3 module) owns the hot path — concurrent fetching and parsing at scale.
- **PostgreSQL** is both the datastore and the work queue. The `crawl_frontier` table *is* the queue: each package has a state (`pending` / `in_progress` / `done` / `failed`), and workers claim work atomically with `SELECT ... FOR UPDATE SKIP LOCKED`. Because the queue state is persisted, the crawl survives being killed and restarted — which is the single most important property of the whole thing.

The schema lives in [`sql/schema.sql`](sql/schema.sql).

## Project status

- [ ] Milestone 1 — Schema + single fetch (Python)
- [x] Milestone 2 — Resumable crawl loop (Python)
- [ ] Milestone 3 — Politeness + throughput (Python)
- [ ] Milestone 4 — Port the hot path to Rust
- [ ] Milestone 5 — Full-registry crawl
- [ ] Milestone 6 — Deep analysis
- [ ] Milestone 7 — Write-up

## Stack

Python, Rust (PyO3 / maturin), PostgreSQL. Built and run on Linux.

## Notes

This README grows as the project does — by the final milestone it becomes the write-up: the architecture decisions, what broke at scale, the Python-vs-Rust benchmark, and the answer to the dependency-depth question.