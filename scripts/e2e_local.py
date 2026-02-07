"""Local end-to-end test for the morning-digest pipeline.

Exercises the full flow against real RSS feeds, real PostgreSQL, and the HTTP API.
No Celery worker needed — calls async functions directly.

Prerequisites:
    docker compose up -d   (PostgreSQL + Redis)

Usage:
    uv run python scripts/e2e_local.py
"""

import asyncio
import subprocess
import sys
import traceback

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from digest.app import create_app
from digest.database import async_session
from digest.models import (
    Article,
    Digest,
    DigestGroup,
    DigestItem,
    Source,
    SourceType,
    User,
    UserInteraction,
    UserTier,
)
from digest.services.pipeline.orchestrator import Orchestrator
from digest.tasks.ingest import ingest_rss_source

E2E_EMAIL = "e2e-test@morning-digest.local"

SOURCES = [
    {
        "type": SourceType.rss,
        "name": "Hacker News Front Page",
        "config": {"url": "https://hnrss.org/frontpage?count=5"},
    },
    {
        "type": SourceType.rss,
        "name": "Hacker News Newest",
        "config": {"url": "https://hnrss.org/newest?count=5"},
    },
]


def step(n: int, title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Step {n}: {title}")
    print(f"{'='*60}")


async def cleanup(db):
    """Delete all data associated with the E2E test user."""
    result = await db.execute(select(User).where(User.email == E2E_EMAIL))
    user = result.scalar_one_or_none()
    if not user:
        return

    source_ids = [
        row[0]
        for row in (
            await db.execute(select(Source.id).where(Source.user_id == user.id))
        ).all()
    ]
    article_ids = []
    if source_ids:
        article_ids = [
            row[0]
            for row in (
                await db.execute(
                    select(Article.id).where(Article.source_id.in_(source_ids))
                )
            ).all()
        ]

    digest_ids = [
        row[0]
        for row in (
            await db.execute(select(Digest.id).where(Digest.user_id == user.id))
        ).all()
    ]
    if digest_ids:
        group_ids = [
            row[0]
            for row in (
                await db.execute(
                    select(DigestGroup.id).where(
                        DigestGroup.digest_id.in_(digest_ids)
                    )
                )
            ).all()
        ]
        if group_ids:
            await db.execute(
                delete(DigestItem).where(DigestItem.group_id.in_(group_ids))
            )
        await db.execute(
            delete(DigestGroup).where(DigestGroup.digest_id.in_(digest_ids))
        )
        await db.execute(delete(Digest).where(Digest.user_id == user.id))

    await db.execute(delete(UserInteraction).where(UserInteraction.user_id == user.id))

    if article_ids:
        await db.execute(delete(Article).where(Article.id.in_(article_ids)))
    if source_ids:
        await db.execute(delete(Source).where(Source.id.in_(source_ids)))

    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    print(f"  Cleaned up previous data for {E2E_EMAIL}")


async def seed(db):
    """Create test user and sources. Returns (user, sources)."""
    user = User(email=E2E_EMAIL, password_hash="not-a-real-hash", tier=UserTier.free)
    db.add(user)
    await db.flush()

    sources = []
    for s in SOURCES:
        source = Source(
            user_id=user.id,
            type=s["type"],
            name=s["name"],
            config=s["config"],
        )
        db.add(source)
        sources.append(source)

    await db.flush()
    await db.commit()

    print(f"  User:    {user.id} ({user.email}, tier={user.tier.value})")
    for s in sources:
        print(f"  Source:  {s.id} ({s.name})")

    return user, sources


async def ingest(db, sources):
    """Fetch real RSS feeds and store articles."""
    total = 0
    for source in sources:
        count = await ingest_rss_source(db, source)
        print(f"  {source.name}: {count} new articles")
        total += count
    await db.commit()
    print(f"  Total: {total} articles ingested")
    if total == 0:
        raise RuntimeError("No articles ingested — check network / feed availability")
    return total


async def generate(db, user):
    """Run the full curation pipeline."""
    orch = Orchestrator()  # No LLM = free tier path
    digest = await orch.generate(db, user.id, user.tier)
    if digest is None:
        raise RuntimeError("Orchestrator returned None — no articles to curate")
    await db.commit()
    print(f"  Digest created: {digest.id} (date={digest.date})")
    return digest


async def verify_db(db, digest):
    """Verify digest structure via direct DB query."""
    result = await db.execute(
        select(Digest)
        .where(Digest.id == digest.id)
        .options(
            selectinload(Digest.groups)
            .selectinload(DigestGroup.items)
            .selectinload(DigestItem.article)
        )
    )
    loaded = result.scalar_one()

    assert len(loaded.groups) >= 1, "Expected at least 1 group"
    print(f"  Digest has {len(loaded.groups)} topic group(s):\n")

    total_articles = 0
    for g in sorted(loaded.groups, key=lambda g: g.sort_order):
        assert g.topic_label, "Group missing topic_label"
        assert len(g.items) >= 1, f"Group '{g.topic_label}' has no items"
        assert g.summary is None, "Free tier should not have group summaries"

        print(f"    [{g.sort_order}] {g.topic_label} ({len(g.items)} article(s))")
        for item in sorted(g.items, key=lambda i: i.sort_order):
            assert item.ai_summary is None, "Free tier should not have AI summaries"
            title = item.article.title[:70]
            primary = " *" if item.is_primary else ""
            print(f"        - {title}{primary}")
            total_articles += 1

    print(f"\n  Total: {total_articles} articles across {len(loaded.groups)} groups")
    return loaded


async def verify_api(user_id, digest_id):
    """Verify digest endpoints via the FastAPI app."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Health check
        r = await client.get("/health")
        assert r.status_code == 200, f"/health returned {r.status_code}"
        print("  GET /health              -> 200 OK")

        # Latest digest
        r = await client.get("/digests/latest", params={"user_id": str(user_id)})
        assert r.status_code == 200, f"/digests/latest returned {r.status_code}"
        body = r.json()
        assert len(body["groups"]) >= 1, "API returned digest with no groups"
        print(f"  GET /digests/latest      -> 200 ({len(body['groups'])} groups)")

        # Get by ID
        r = await client.get(f"/digests/{digest_id}")
        assert r.status_code == 200, f"/digests/{{id}} returned {r.status_code}"
        print(f"  GET /digests/{{id}}        -> 200")

        # List digests
        r = await client.get("/digests/", params={"user_id": str(user_id)})
        assert r.status_code == 200, f"/digests/ returned {r.status_code}"
        items = r.json()
        assert len(items) >= 1, "Digest list is empty"
        print(f"  GET /digests/            -> 200 ({len(items)} digest(s))")


async def main():
    failed = False
    user = None

    try:
        # Step 1: Migrations
        step(1, "Run Alembic migrations")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  FAILED:\n{result.stderr}")
            sys.exit(1)
        print("  Migrations applied successfully")

        async with async_session() as db:
            # Step 2: Cleanup
            step(2, "Clean up previous test data")
            await cleanup(db)

            # Step 3: Seed
            step(3, "Seed test user and sources")
            user, sources = await seed(db)

            # Step 4: Ingest
            step(4, "Ingest RSS feeds (live network)")
            await ingest(db, sources)

            # Step 5: Generate digest
            step(5, "Generate digest (free tier, TF-IDF)")
            digest = await generate(db, user)

            # Step 6: Verify DB
            step(6, "Verify digest via database")
            await verify_db(db, digest)

        # Step 7: Verify API (uses its own sessions)
        step(7, "Verify digest via HTTP API")
        await verify_api(user.id, digest.id)

        print(f"\n{'='*60}")
        print("  E2E TEST PASSED")
        print(f"{'='*60}\n")

    except Exception:
        failed = True
        traceback.print_exc()
        print(f"\n{'='*60}")
        print("  E2E TEST FAILED")
        print(f"{'='*60}\n")

    finally:
        # Always clean up
        try:
            async with async_session() as db:
                await cleanup(db)
        except Exception:
            pass

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
