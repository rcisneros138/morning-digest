from digest.ingestion.rss import ParsedArticle, RSSIngester


class RedditIngester:
    def __init__(self):
        self.rss_ingester = RSSIngester()

    def build_feed_url(self, subreddit: str) -> str:
        name = subreddit.strip("/")
        if name.startswith("r/"):
            name = name[2:]
        return f"https://www.reddit.com/r/{name}/.rss"

    async def fetch_subreddit(self, subreddit: str) -> list[ParsedArticle]:
        url = self.build_feed_url(subreddit)
        return await self.rss_ingester.fetch_feed(url)
