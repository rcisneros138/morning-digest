from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from digest.ingestion.rss import RSSIngester, ParsedArticle


def _make_feed_entry(title, link, summary, published=None):
    """Build a mock feedparser entry."""
    entry = {
        "title": title,
        "link": link,
        "summary": summary,
    }
    if published:
        entry["published_parsed"] = published.timetuple()
    return type("Entry", (), entry)()


def _make_feed(entries, status=200):
    feed = type("Feed", (), {
        "entries": entries,
        "status": status,
        "bozo": False,
    })()
    return feed


class TestRSSIngester:
    def test_parse_entry_extracts_fields(self):
        entry = _make_feed_entry(
            title="Test Article",
            link="https://example.com/article",
            summary="<p>This is the summary.</p>",
            published=datetime(2026, 2, 4, 8, 0, tzinfo=timezone.utc),
        )
        ingester = RSSIngester()
        parsed = ingester.parse_entry(entry)

        assert parsed.title == "Test Article"
        assert parsed.url == "https://example.com/article"
        assert parsed.content_html == "<p>This is the summary.</p>"
        assert parsed.content_text == "This is the summary."
        assert parsed.published_at.year == 2026

    def test_parse_entry_handles_missing_date(self):
        entry = _make_feed_entry(
            title="No Date",
            link="https://example.com/nodate",
            summary="Content here",
        )
        ingester = RSSIngester()
        parsed = ingester.parse_entry(entry)

        assert parsed.title == "No Date"
        assert parsed.published_at is None

    def test_parse_entry_strips_html_for_text(self):
        entry = _make_feed_entry(
            title="HTML Test",
            link="https://example.com/html",
            summary="<h1>Header</h1><p>Paragraph with <b>bold</b> text.</p>",
        )
        ingester = RSSIngester()
        parsed = ingester.parse_entry(entry)

        assert "<" not in parsed.content_text
        assert "bold" in parsed.content_text

    def test_parse_entry_generates_fingerprint(self):
        entry = _make_feed_entry(
            title="Fingerprint Test",
            link="https://example.com/fp",
            summary="Some content for fingerprinting",
        )
        ingester = RSSIngester()
        parsed = ingester.parse_entry(entry)

        assert parsed.fingerprint is not None
        assert len(parsed.fingerprint) == 64  # sha256 hex

    async def test_fetch_feed_returns_parsed_articles(self):
        entries = [
            _make_feed_entry("Article 1", "https://example.com/1", "Summary 1"),
            _make_feed_entry("Article 2", "https://example.com/2", "Summary 2"),
        ]
        feed = _make_feed(entries)

        ingester = RSSIngester()
        with patch("digest.ingestion.rss.feedparser.parse", return_value=feed):
            articles = await ingester.fetch_feed("https://example.com/rss")

        assert len(articles) == 2
        assert articles[0].title == "Article 1"
        assert articles[1].title == "Article 2"

    async def test_fetch_feed_skips_entries_without_title(self):
        entries = [
            _make_feed_entry("Good Article", "https://example.com/good", "Content"),
            _make_feed_entry("", "https://example.com/empty", "No title"),
        ]
        feed = _make_feed(entries)

        ingester = RSSIngester()
        with patch("digest.ingestion.rss.feedparser.parse", return_value=feed):
            articles = await ingester.fetch_feed("https://example.com/rss")

        assert len(articles) == 1
        assert articles[0].title == "Good Article"
