import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from digest.database import async_session
from digest.ingestion.reddit import RedditIngester
from digest.ingestion.rss import RSSIngester
from digest.models import Source, SourceType
from digest.services.article_store import ArticleStore
from digest.worker import celery_app


async def ingest_rss_source(db: AsyncSession, source: Source) -> int:
    ingester = RSSIngester()
    url = source.config.get("url")
    if not url:
        return 0

    articles = await ingester.fetch_feed(url)
    store = ArticleStore(db)
    stored = await store.store_batch(source.id, articles)

    source.last_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()

    return len(stored)


async def ingest_reddit_source(db: AsyncSession, source: Source) -> int:
    ingester = RedditIngester()
    subreddit = source.config.get("subreddit")
    if not subreddit:
        return 0

    articles = await ingester.fetch_subreddit(subreddit)
    store = ArticleStore(db)
    stored = await store.store_batch(source.id, articles)

    source.last_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()

    return len(stored)


async def _poll_all_feeds():
    async with async_session() as db:
        result = await db.execute(
            select(Source).where(
                Source.is_active.is_(True),
                Source.type.in_([SourceType.rss, SourceType.reddit]),
            )
        )
        sources = result.scalars().all()

        for source in sources:
            if source.type == SourceType.rss:
                await ingest_rss_source(db, source)
            elif source.type == SourceType.reddit:
                await ingest_reddit_source(db, source)

        await db.commit()


@celery_app.task(name="digest.tasks.ingest.poll_all_rss_feeds")
def poll_all_rss_feeds():
    asyncio.run(_poll_all_feeds())
