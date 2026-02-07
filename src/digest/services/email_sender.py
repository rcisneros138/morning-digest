from __future__ import annotations

import logging

import httpx

from digest.config import settings
from digest.models import Digest, User

logger = logging.getLogger(__name__)


class EmailSender:
    async def send_digest(self, user: User, digest: Digest) -> bool:
        if not settings.mailgun_api_key or not settings.mailgun_domain:
            logger.warning("Mailgun not configured, skipping email for user %s", user.id)
            return False

        html = self._render_html(digest)
        text = self._render_text(digest)
        subject = f"Your Morning Digest - {digest.date}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.mailgun.net/v3/{settings.mailgun_domain}/messages",
                    auth=("api", settings.mailgun_api_key),
                    data={
                        "from": settings.mailgun_from_email,
                        "to": user.email,
                        "subject": subject,
                        "html": html,
                        "text": text,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                logger.info("Sent digest email to %s", user.email)
                return True
        except Exception:
            logger.exception("Failed to send digest email to %s", user.email)
            return False

    async def send_password_reset(self, user: User, token: str) -> bool:
        if not settings.mailgun_api_key or not settings.mailgun_domain:
            logger.warning("Mailgun not configured, skipping password reset email for user %s", user.id)
            return False

        html = (
            "<!DOCTYPE html>"
            "<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto;padding:16px;'>"
            "<h1 style='color:#222;font-size:22px;'>Password Reset</h1>"
            "<p>Use the following token to reset your password. It expires in 1 hour.</p>"
            f"<p style='font-family:monospace;background:#f5f5f5;padding:12px;border-radius:4px;word-break:break-all;'>{token}</p>"
            "<p style='color:#999;font-size:12px;'>If you didn't request this, you can safely ignore this email.</p>"
            "</body></html>"
        )
        text = (
            "Password Reset\n\n"
            "Use the following token to reset your password. It expires in 1 hour.\n\n"
            f"{token}\n\n"
            "If you didn't request this, you can safely ignore this email."
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.mailgun.net/v3/{settings.mailgun_domain}/messages",
                    auth=("api", settings.mailgun_api_key),
                    data={
                        "from": settings.mailgun_from_email,
                        "to": user.email,
                        "subject": "Password Reset - Morning Digest",
                        "html": html,
                        "text": text,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                logger.info("Sent password reset email to %s", user.email)
                return True
        except Exception:
            logger.exception("Failed to send password reset email to %s", user.email)
            return False

    def _render_html(self, digest: Digest) -> str:
        groups_html = ""
        for group in digest.groups:
            items_html = ""
            for item in group.items:
                article = item.article
                link = (
                    f'<a href="{article.url}" style="color:#1a73e8;">{article.title}</a>'
                    if article.url
                    else article.title
                )
                summary = f"<p style='margin:4px 0 0;color:#555;'>{item.ai_summary}</p>" if item.ai_summary else ""
                items_html += f"<li style='margin-bottom:12px;'>{link}{summary}</li>"

            group_summary = f"<p style='color:#666;margin:4px 0 8px;'>{group.summary}</p>" if group.summary else ""
            groups_html += (
                f"<h2 style='color:#333;font-size:18px;margin:24px 0 8px;'>{group.topic_label}</h2>"
                f"{group_summary}"
                f"<ul style='padding-left:20px;'>{items_html}</ul>"
            )

        return (
            "<!DOCTYPE html>"
            "<html><body style='font-family:sans-serif;max-width:600px;margin:0 auto;padding:16px;'>"
            f"<h1 style='color:#222;font-size:22px;'>Morning Digest - {digest.date}</h1>"
            f"{groups_html}"
            "<hr style='border:none;border-top:1px solid #eee;margin:24px 0;'/>"
            "<p style='color:#999;font-size:12px;'>Sent by Morning Digest</p>"
            "</body></html>"
        )

    def _render_text(self, digest: Digest) -> str:
        lines = [f"Morning Digest - {digest.date}", "=" * 40, ""]
        for group in digest.groups:
            lines.append(group.topic_label)
            lines.append("-" * len(group.topic_label))
            if group.summary:
                lines.append(group.summary)
                lines.append("")
            for item in group.items:
                article = item.article
                lines.append(f"  * {article.title}")
                if article.url:
                    lines.append(f"    {article.url}")
                if item.ai_summary:
                    lines.append(f"    {item.ai_summary}")
                lines.append("")
            lines.append("")
        return "\n".join(lines)
