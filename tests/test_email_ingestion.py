import pytest

from digest.ingestion.email import EmailIngester, ParsedEmail


class TestEmailIngester:
    def test_parse_raw_email_extracts_fields(self):
        ingester = EmailIngester()
        result = ingester.parse_inbound(
            sender="newsletter@morningbrew.com",
            subject="Morning Brew - Feb 4",
            body_html="<h1>Top Stories</h1><p>The Fed held rates steady.</p>",
            body_plain="Top Stories\nThe Fed held rates steady.",
            recipient="user-abc123@digest.app",
        )

        assert result.sender == "newsletter@morningbrew.com"
        assert result.subject == "Morning Brew - Feb 4"
        assert "Fed held rates" in result.content_text
        assert result.content_html is not None
        assert result.forwarding_address == "user-abc123@digest.app"

    def test_parse_inbound_strips_html_for_text_when_no_plain(self):
        ingester = EmailIngester()
        result = ingester.parse_inbound(
            sender="news@example.com",
            subject="Weekly Update",
            body_html="<p>Important <b>news</b> here.</p>",
            body_plain=None,
            recipient="user-xyz@digest.app",
        )

        assert "<" not in result.content_text
        assert "news" in result.content_text

    def test_parse_inbound_generates_fingerprint(self):
        ingester = EmailIngester()
        result = ingester.parse_inbound(
            sender="news@example.com",
            subject="Test Subject",
            body_html="<p>Content</p>",
            body_plain="Content",
            recipient="user-xyz@digest.app",
        )

        assert result.fingerprint is not None
        assert len(result.fingerprint) == 64

    def test_extract_forwarding_id(self):
        ingester = EmailIngester()
        assert ingester.extract_forwarding_id("user-abc123@digest.app") == "user-abc123"
        assert ingester.extract_forwarding_id("test-xyz@digest.app") == "test-xyz"

    def test_prefers_plain_text_when_available(self):
        ingester = EmailIngester()
        result = ingester.parse_inbound(
            sender="news@example.com",
            subject="Test",
            body_html="<p>HTML version</p>",
            body_plain="Plain text version",
            recipient="user@digest.app",
        )

        assert result.content_text == "Plain text version"
