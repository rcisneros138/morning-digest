from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from digest.models import UserTier
from digest.tasks.generate_digest import _is_digest_time


def _make_user(timezone="UTC", digest_time="06:00", tier=UserTier.free):
    return SimpleNamespace(timezone=timezone, digest_time=digest_time, tier=tier)


class TestIsDigestTime:
    def test_matches_utc_user(self):
        user = _make_user(timezone="UTC", digest_time="06:00")
        now = datetime(2026, 2, 1, 6, 0, tzinfo=UTC)
        assert _is_digest_time(user, now) is True

    def test_no_match_wrong_hour(self):
        user = _make_user(timezone="UTC", digest_time="06:00")
        now = datetime(2026, 2, 1, 7, 0, tzinfo=UTC)
        assert _is_digest_time(user, now) is False

    def test_no_match_wrong_minute(self):
        user = _make_user(timezone="UTC", digest_time="06:00")
        now = datetime(2026, 2, 1, 6, 1, tzinfo=UTC)
        assert _is_digest_time(user, now) is False

    def test_timezone_conversion(self):
        # User in US/Eastern (UTC-5), wants digest at 06:00 local
        user = _make_user(timezone="US/Eastern", digest_time="06:00")
        # 11:00 UTC = 06:00 Eastern (standard time)
        now = datetime(2026, 2, 1, 11, 0, tzinfo=UTC)
        assert _is_digest_time(user, now) is True

    def test_timezone_conversion_no_match(self):
        user = _make_user(timezone="US/Eastern", digest_time="06:00")
        # 06:00 UTC = 01:00 Eastern, should not match
        now = datetime(2026, 2, 1, 6, 0, tzinfo=UTC)
        assert _is_digest_time(user, now) is False

    def test_invalid_timezone_defaults_to_utc(self):
        user = _make_user(timezone="Invalid/Zone", digest_time="06:00")
        now = datetime(2026, 2, 1, 6, 0, tzinfo=UTC)
        assert _is_digest_time(user, now) is True

    def test_custom_digest_time(self):
        user = _make_user(timezone="UTC", digest_time="14:30")
        now = datetime(2026, 2, 1, 14, 30, tzinfo=UTC)
        assert _is_digest_time(user, now) is True


class TestCheckSchedule:
    async def test_dispatches_for_matching_user(self):
        user = _make_user(timezone="UTC", digest_time="06:00")
        user.id = "test-user-id"

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_db.scalars = AsyncMock(return_value=AsyncMock(all=lambda: [user]))

        mock_delay = AsyncMock()

        with (
            patch("digest.tasks.generate_digest.async_session", return_value=mock_db),
            patch("digest.tasks.generate_digest.datetime") as mock_dt,
            patch("digest.tasks.generate_digest.generate_user_digest") as mock_task,
        ):
            mock_dt.now.return_value = datetime(2026, 2, 1, 6, 0, tzinfo=UTC)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            mock_task.delay = mock_delay

            from digest.tasks.generate_digest import _check_schedule

            await _check_schedule()

            mock_delay.assert_called_once_with("test-user-id")


class TestBeatSchedule:
    def test_beat_includes_digest_check(self):
        from digest.worker import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "check-digest-schedule" in schedule
        assert (
            schedule["check-digest-schedule"]["task"]
            == "digest.tasks.generate_digest.check_digest_schedule"
        )
