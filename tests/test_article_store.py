import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from digest.ingestion.rss import ParsedArticle
from digest.models import Article, Source, SourceType, User
from digest.services.article_store import ArticleStore


async def _create_user_and_source(db) -> tuple:
    user = User(email=f"{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
    db.add(user)
    await db.flush()

    source = Source(user_id=user.id, type=SourceType.rss, name="Test Feed")
    db.add(source)
    await db.flush()

    return user, source


class TestArticleStore:
    async def test_store_new_article(self, db):
        _, source = await _create_user_and_source(db)

        parsed = ParsedArticle(
            title="New Article",
            url="https://example.com/new",
            content_html="<p>Content</p>",
            content_text="Content",
            author="Author",
            published_at=datetime(2026, 2, 4),
            fingerprint="abc123fingerprint",
        )

        store = ArticleStore(db)
        article = await store.store_article(source.id, parsed)

        assert article.id is not None
        assert article.title == "New Article"
        assert article.source_id == source.id

    async def test_skips_duplicate_fingerprint(self, db):
        _, source = await _create_user_and_source(db)
        fingerprint = "duplicate_fingerprint_value"

        parsed = ParsedArticle(
            title="Original",
            url="https://example.com/orig",
            content_html="<p>Content</p>",
            content_text="Content",
            author=None,
            published_at=None,
            fingerprint=fingerprint,
        )

        store = ArticleStore(db)
        first = await store.store_article(source.id, parsed)
        assert first is not None

        parsed_dup = ParsedArticle(
            title="Duplicate",
            url="https://example.com/dup",
            content_html="<p>Dup</p>",
            content_text="Dup",
            author=None,
            published_at=None,
            fingerprint=fingerprint,
        )
        second = await store.store_article(source.id, parsed_dup)
        assert second is None

    async def test_store_batch(self, db):
        _, source = await _create_user_and_source(db)

        articles = [
            ParsedArticle(
                title=f"Article {i}",
                url=f"https://example.com/{i}",
                content_html=f"<p>Content {i}</p>",
                content_text=f"Content {i}",
                author=None,
                published_at=None,
                fingerprint=f"unique_fp_{i}",
            )
            for i in range(5)
        ]

        store = ArticleStore(db)
        stored = await store.store_batch(source.id, articles)

        assert len(stored) == 5

        result = await db.execute(select(Article).where(Article.source_id == source.id))
        assert len(result.scalars().all()) == 5
