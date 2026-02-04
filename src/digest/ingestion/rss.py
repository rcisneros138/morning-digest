import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from time import mktime

import feedparser
from bs4 import BeautifulSoup

from digest.models import Article


@dataclass
class ParsedArticle:
    title: str
    url: str | None
    content_html: str | None
    content_text: str | None
    author: str | None
    published_at: datetime | None
    fingerprint: str


class RSSIngester:
    def _strip_html(self, html: str) -> str:
        return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)

    def parse_entry(self, entry) -> ParsedArticle:
        title = getattr(entry, "title", "") or ""
        link = getattr(entry, "link", None)
        summary = getattr(entry, "summary", "") or ""
        author = getattr(entry, "author", None)

        # Try content:encoded first (full article), fall back to summary
        content_html = summary
        content_entries = getattr(entry, "content", None)
        if content_entries and len(content_entries) > 0:
            content_html = content_entries[0].get("value", summary)

        content_text = self._strip_html(content_html)

        published_at = None
        published_parsed = getattr(entry, "published_parsed", None)
        if published_parsed:
            published_at = datetime.fromtimestamp(mktime(published_parsed), tz=timezone.utc)

        fingerprint = Article.generate_fingerprint(title, content_text)

        return ParsedArticle(
            title=title,
            url=link,
            content_html=content_html,
            content_text=content_text,
            author=author,
            published_at=published_at,
            fingerprint=fingerprint,
        )

    async def fetch_feed(self, url: str) -> list[ParsedArticle]:
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, url)

        articles = []
        for entry in feed.entries:
            parsed = self.parse_entry(entry)
            if not parsed.title.strip():
                continue
            articles.append(parsed)

        return articles
