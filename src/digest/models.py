import enum
import hashlib
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserTier(str, enum.Enum):
    free = "free"
    paid = "paid"


class SourceType(str, enum.Enum):
    newsletter = "newsletter"
    rss = "rss"
    reddit = "reddit"


class InteractionType(str, enum.Enum):
    read = "read"
    tapped_through = "tapped_through"
    saved = "saved"
    dismissed = "dismissed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[UserTier] = mapped_column(Enum(UserTier), default=UserTier.free)
    timezone: Mapped[str] = mapped_column(Text, default="UTC")
    digest_time: Mapped[str] = mapped_column(Text, default="06:00")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    sources: Mapped[list["Source"]] = relationship(back_populates="user")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="sources")
    articles: Mapped[list["Article"]] = relationship(back_populates="source")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    source: Mapped["Source"] = relationship(back_populates="articles")

    @staticmethod
    def generate_fingerprint(title: str, content_text: str) -> str:
        normalized = f"{title.lower().strip()}:{content_text[:200].lower().strip()}"
        return hashlib.sha256(normalized.encode()).hexdigest()


class Digest(Base):
    __tablename__ = "digests"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_digest_user_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    tier_at_creation: Mapped[UserTier] = mapped_column(Enum(UserTier), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship()
    groups: Mapped[list["DigestGroup"]] = relationship(
        back_populates="digest", order_by="DigestGroup.sort_order"
    )


class DigestGroup(Base):
    __tablename__ = "digest_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    digest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("digests.id"), nullable=False)
    topic_label: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    digest: Mapped["Digest"] = relationship(back_populates="groups")
    items: Mapped[list["DigestItem"]] = relationship(
        back_populates="group", order_by="DigestItem.sort_order"
    )


class DigestItem(Base):
    __tablename__ = "digest_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("digest_groups.id"), nullable=False)
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    group: Mapped["DigestGroup"] = relationship(back_populates="items")
    article: Mapped["Article"] = relationship()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship()


class UserInteraction(Base):
    __tablename__ = "user_interactions"
    __table_args__ = (Index("ix_user_interactions_user_type", "user_id", "type"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), nullable=False)
    type: Mapped[InteractionType] = mapped_column(Enum(InteractionType), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
