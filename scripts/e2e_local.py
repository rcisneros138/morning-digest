"""Local end-to-end test for the morning-digest pipeline.

Exercises the full user journey: register, add sources, ingest, generate digest,
verify via authenticated API, refresh tokens, logout.
No Celery worker needed — calls async functions directly.

Prerequisites:
    docker compose up -d   (PostgreSQL + Redis)
    JWT_SECRET_KEY set in .env (any string works for testing)

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

from digest.database import async_session
from digest.models import (
    Article,
    Digest,
    DigestGroup,
    DigestItem,
    RefreshToken,
    Source,
    SourceType,
    User,
    UserInteraction,
)
from digest.services.pipeline.orchestrator import Orchestrator
from digest.tasks.ingest import ingest_rss_source

E2E_EMAIL = "e2e-test@example.com"
E2E_PASSWORD = "e2e-test-password-123"

SOURCES = [
    {
        "type": "rss",
        "name": "Hacker News Front Page",
        "config": {"url": "https://hnrss.org/frontpage?count=5"},
    },
    {
        "type": "rss",
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
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))

    if article_ids:
        await db.execute(delete(Article).where(Article.id.in_(article_ids)))
    if source_ids:
        await db.execute(delete(Source).where(Source.id.in_(source_ids)))

    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    print(f"  Cleaned up previous data for {E2E_EMAIL}")


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def register(client) -> dict:
    """Register a new user via the API. Returns auth response."""
    r = await client.post(
        "/auth/register",
        json={"email": E2E_EMAIL, "password": E2E_PASSWORD},
    )
    assert r.status_code == 201, f"/auth/register returned {r.status_code}: {r.text}"
    data = r.json()
    assert "user_id" in data
    assert "access_token" in data
    assert "refresh_token" in data
    print(f"  POST /auth/register      -> 201")
    print(f"  User ID: {data['user_id']}")
    return data


async def add_sources(client, token: str) -> list[dict]:
    """Add sources via the API. Returns list of created sources."""
    created = []
    for s in SOURCES:
        r = await client.post(
            "/sources/",
            json=s,
            headers=auth_headers(token),
        )
        assert r.status_code == 201, f"POST /sources/ returned {r.status_code}: {r.text}"
        source = r.json()
        created.append(source)
        print(f"  POST /sources/           -> 201 ({source['name']})")

    # Verify list
    r = await client.get("/sources/", headers=auth_headers(token))
    assert r.status_code == 200
    sources = r.json()
    assert len(sources) == len(SOURCES), f"Expected {len(SOURCES)} sources, got {len(sources)}"
    print(f"  GET  /sources/           -> 200 ({len(sources)} sources)")

    return created


async def ingest(db, user_id):
    """Fetch real RSS feeds and store articles."""
    sources = (
        await db.scalars(select(Source).where(Source.user_id == user_id))
    ).all()

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


async def generate(db, user_id):
    """Run the full curation pipeline."""
    user = await db.get(User, user_id)
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


async def verify_api(client, token: str, digest_id: str):
    """Verify digest endpoints with JWT auth."""
    headers = auth_headers(token)

    # Health check (no auth needed)
    r = await client.get("/health")
    assert r.status_code == 200, f"/health returned {r.status_code}"
    print("  GET /health              -> 200 OK")

    # Latest digest
    r = await client.get("/digests/latest", headers=headers)
    assert r.status_code == 200, f"/digests/latest returned {r.status_code}: {r.text}"
    body = r.json()
    assert len(body["groups"]) >= 1, "API returned digest with no groups"
    print(f"  GET /digests/latest      -> 200 ({len(body['groups'])} groups)")

    # Get by ID
    r = await client.get(f"/digests/{digest_id}", headers=headers)
    assert r.status_code == 200, f"/digests/{{id}} returned {r.status_code}: {r.text}"
    print(f"  GET /digests/{{id}}        -> 200")

    # List digests
    r = await client.get("/digests/", headers=headers)
    assert r.status_code == 200, f"/digests/ returned {r.status_code}: {r.text}"
    items = r.json()
    assert len(items) >= 1, "Digest list is empty"
    print(f"  GET /digests/            -> 200 ({len(items)} digest(s))")

    # Unauthenticated request should fail
    r = await client.get("/digests/latest")
    assert r.status_code in (401, 403), f"Expected 401/403 without auth, got {r.status_code}"
    print(f"  GET /digests/latest (no auth) -> {r.status_code} (correct)")


async def verify_token_lifecycle(client, refresh_token: str):
    """Test refresh token rotation and logout."""
    # Refresh
    r = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200, f"/auth/refresh returned {r.status_code}: {r.text}"
    data = r.json()
    new_access = data["access_token"]
    new_refresh = data["refresh_token"]
    assert new_refresh != refresh_token, "Refresh token was not rotated"
    print(f"  POST /auth/refresh       -> 200 (token rotated)")

    # Old refresh token should be rejected
    r = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 401, f"Old refresh token should be rejected, got {r.status_code}"
    print(f"  POST /auth/refresh (old) -> 401 (correct)")

    # New access token should work
    r = await client.get("/digests/latest", headers=auth_headers(new_access))
    assert r.status_code in (200, 404), f"New access token failed: {r.status_code}"
    print(f"  GET /digests/latest (new token) -> {r.status_code} (valid)")

    # Logout
    r = await client.post("/auth/logout", json={"refresh_token": new_refresh})
    assert r.status_code == 200, f"/auth/logout returned {r.status_code}: {r.text}"
    print(f"  POST /auth/logout        -> 200")

    # Refresh after logout should fail
    r = await client.post("/auth/refresh", json={"refresh_token": new_refresh})
    assert r.status_code == 401, f"Post-logout refresh should fail, got {r.status_code}"
    print(f"  POST /auth/refresh (post-logout) -> 401 (correct)")

    return new_access


async def verify_login(client):
    """Test login with existing credentials."""
    r = await client.post(
        "/auth/login",
        json={"email": E2E_EMAIL, "password": E2E_PASSWORD},
    )
    assert r.status_code == 200, f"/auth/login returned {r.status_code}: {r.text}"
    data = r.json()
    assert "access_token" in data
    print(f"  POST /auth/login         -> 200")
    return data


async def main():
    failed = False

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

        # Step 3-4: Register and add sources via API
        from digest.app import create_app

        app = create_app()
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            step(3, "Register user via API")
            auth_data = await register(client)
            user_id = auth_data["user_id"]
            access_token = auth_data["access_token"]
            refresh_token = auth_data["refresh_token"]

            step(4, "Add sources via API")
            await add_sources(client, access_token)

        # Step 5-6: Ingest and generate (direct async, need DB)
        async with async_session() as db:
            step(5, "Ingest RSS feeds (live network)")
            await ingest(db, user_id)

            step(6, "Generate digest (free tier, TF-IDF)")
            digest = await generate(db, user_id)

            # Step 7: Verify DB
            step(7, "Verify digest via database")
            await verify_db(db, digest)
            digest_id = str(digest.id)

        # Step 8-10: Verify API with auth (new app instance for fresh sessions)
        app = create_app()
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            step(8, "Verify digest API (authenticated)")
            await verify_api(client, access_token, digest_id)

            step(9, "Verify token refresh + logout lifecycle")
            await verify_token_lifecycle(client, refresh_token)

            step(10, "Verify login with existing credentials")
            await verify_login(client)

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
