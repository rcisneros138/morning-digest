import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from digest.ingestion.rss import ParsedArticle
from digest.models import Article


class ArticleStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _fingerprint_exists(self, source_id: uuid.UUID, fingerprint: str) -> bool:
        result = await self.db.execute(
            select(Article.id).where(
                Article.source_id == source_id,
                Article.fingerprint == fingerprint,
            )
        )
        return result.scalar_one_or_none() is not None

    async def store_article(
        self, source_id: uuid.UUID, parsed: ParsedArticle
    ) -> Article | None:
        if await self._fingerprint_exists(source_id, parsed.fingerprint):
            return None

        article = Article(
            source_id=source_id,
            title=parsed.title,
            url=parsed.url,
            content_html=parsed.content_html,
            content_text=parsed.content_text,
            author=parsed.author,
            published_at=parsed.published_at,
            fingerprint=parsed.fingerprint,
        )
        self.db.add(article)
        await self.db.flush()
        return article

    async def store_batch(
        self, source_id: uuid.UUID, articles: list[ParsedArticle]
    ) -> list[Article]:
        stored = []
        for parsed in articles:
            article = await self.store_article(source_id, parsed)
            if article is not None:
                stored.append(article)
        return stored
