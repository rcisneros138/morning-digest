from unittest.mock import AsyncMock, patch

import pytest

from digest.ingestion.reddit import RedditIngester


class TestRedditIngester:
    def test_build_feed_url_from_subreddit_name(self):
        ingester = RedditIngester()
        assert ingester.build_feed_url("python") == "https://www.reddit.com/r/python/.rss"

    def test_build_feed_url_strips_r_prefix(self):
        ingester = RedditIngester()
        assert ingester.build_feed_url("r/python") == "https://www.reddit.com/r/python/.rss"

    def test_build_feed_url_strips_slash_prefix(self):
        ingester = RedditIngester()
        assert ingester.build_feed_url("/r/python") == "https://www.reddit.com/r/python/.rss"

    @pytest.mark.asyncio
    async def test_fetch_subreddit_uses_rss_ingester(self):
        ingester = RedditIngester()

        mock_articles = [
            type("PA", (), {"title": "Post 1", "url": "https://reddit.com/1"})(),
            type("PA", (), {"title": "Post 2", "url": "https://reddit.com/2"})(),
        ]

        with patch.object(
            ingester.rss_ingester, "fetch_feed", new_callable=AsyncMock, return_value=mock_articles
        ) as mock_fetch:
            results = await ingester.fetch_subreddit("python")

            assert len(results) == 2
            mock_fetch.assert_called_once_with(
                "https://www.reddit.com/r/python/.rss"
            )
