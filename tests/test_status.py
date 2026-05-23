from crawler.status import CrawlStatus, format_status


def test_format_status_with_failures():
    snapshot = CrawlStatus(
        frontier={"pending": 3, "in_progress": 1, "done": 8, "failed": 2},
        packages=8,
        versions=15,
        dependencies=42,
        recent_failures=[("timeout", 2)],
    )

    assert format_status(snapshot) == "\n".join(
        [
            "crawl status",
            "frontier: pending=3 in_progress=1 done=8 failed=2",
            "stored: packages=8 versions=15 dependencies=42",
            "failure reasons:",
            "  2x timeout",
        ]
    )


def test_format_status_without_failures():
    snapshot = CrawlStatus(
        frontier={},
        packages=0,
        versions=0,
        dependencies=0,
        recent_failures=[],
    )

    assert "failure reasons: none" in format_status(snapshot)
