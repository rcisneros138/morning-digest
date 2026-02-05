import asyncio
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from digest.database import async_session
from digest.models import User
from digest.services.llm import LLMService
from digest.services.pipeline.orchestrator import Orchestrator
from digest.worker import celery_app

logger = logging.getLogger(__name__)


def _is_digest_time(user: User, now_utc: datetime) -> bool:
    """Check if current UTC time matches the user's configured digest time in their timezone."""
    try:
        tz = ZoneInfo(user.timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    user_now = now_utc.astimezone(tz)
    # Parse user's digest_time (HH:MM format)
    parts = (user.digest_time or "06:00").split(":")
    target_hour = int(parts[0])
    target_minute = int(parts[1]) if len(parts) > 1 else 0

    return user_now.hour == target_hour and user_now.minute == target_minute


async def _check_schedule():
    now_utc = datetime.now(UTC)

    async with async_session() as db:
        users = (await db.scalars(select(User))).all()

        for user in users:
            if _is_digest_time(user, now_utc):
                generate_user_digest.delay(str(user.id))


async def _generate_for_user(user_id_str: str):
    async with async_session() as db:
        user = await db.get(User, user_id_str)
        if not user:
            logger.error("User %s not found", user_id_str)
            return

        llm = LLMService() if user.tier.value == "paid" else None
        orch = Orchestrator(llm=llm)
        digest = await orch.generate(db, user.id, user.tier)

        if digest:
            await db.commit()
            logger.info("Generated digest %s for user %s", digest.id, user_id_str)
        else:
            logger.info("No articles to curate for user %s", user_id_str)


@celery_app.task(name="digest.tasks.generate_digest.check_digest_schedule")
def check_digest_schedule():
    asyncio.run(_check_schedule())


@celery_app.task(name="digest.tasks.generate_digest.generate_user_digest")
def generate_user_digest(user_id: str):
    asyncio.run(_generate_for_user(user_id))
