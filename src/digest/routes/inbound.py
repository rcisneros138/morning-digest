from fastapi import APIRouter, Form, Response

from sqlalchemy import select

from digest.database import async_session
from digest.ingestion.email import EmailIngester
from digest.ingestion.rss import ParsedArticle
from digest.models import Source, SourceType
from digest.services.article_store import ArticleStore

router = APIRouter()


@router.post("/webhooks/inbound")
async def inbound_email(
    sender: str = Form(...),
    subject: str = Form(...),
    recipient: str = Form(...),
    body_html: str = Form(None, alias="body-html"),
    body_plain: str = Form(None, alias="body-plain"),
):
    async with async_session() as db:
        # Find the source by forwarding address
        result = await db.execute(
            select(Source).where(
                Source.type == SourceType.newsletter,
                Source.config["forwarding_address"].astext == recipient,
            )
        )
        source = result.scalar_one_or_none()

        if source is None:
            return Response(status_code=406, content="Unknown recipient")

        ingester = EmailIngester()
        parsed = ingester.parse_inbound(
            sender=sender,
            subject=subject,
            body_html=body_html,
            body_plain=body_plain,
            recipient=recipient,
        )

        article = ParsedArticle(
            title=parsed.subject,
            url=None,
            content_html=parsed.content_html,
            content_text=parsed.content_text,
            author=parsed.sender,
            published_at=None,
            fingerprint=parsed.fingerprint,
        )

        store = ArticleStore(db)
        await store.store_article(source.id, article)
        await db.commit()

    return {"status": "accepted"}
