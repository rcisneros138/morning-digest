from dataclasses import dataclass

from bs4 import BeautifulSoup

from digest.models import Article


@dataclass
class ParsedEmail:
    sender: str
    subject: str
    content_html: str | None
    content_text: str
    forwarding_address: str
    fingerprint: str


class EmailIngester:
    def _strip_html(self, html: str) -> str:
        return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)

    def parse_inbound(
        self,
        sender: str,
        subject: str,
        body_html: str | None,
        body_plain: str | None,
        recipient: str,
    ) -> ParsedEmail:
        if body_plain:
            content_text = body_plain
        elif body_html:
            content_text = self._strip_html(body_html)
        else:
            content_text = ""

        fingerprint = Article.generate_fingerprint(subject, content_text)

        return ParsedEmail(
            sender=sender,
            subject=subject,
            content_html=body_html,
            content_text=content_text,
            forwarding_address=recipient,
            fingerprint=fingerprint,
        )

    def extract_forwarding_id(self, email_address: str) -> str:
        return email_address.split("@")[0]
