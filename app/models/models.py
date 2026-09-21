from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class MailboxType(str, Enum):
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"


class DomainStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    DISABLED = "disabled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(
        Text,
    )

    country: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    country_code: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    role: Mapped[str] = mapped_column(
        String(20),
        default=UserRole.USER.value,
        nullable=False,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    mailboxes: Mapped[list["Mailbox"]] = relationship(
        back_populates="user",
    )


class GuestSession(Base):
    __tablename__ = "guest_sessions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    session_token: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
    )

    country: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    country_code: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    mailboxes: Mapped[list["Mailbox"]] = relationship(
        back_populates="guest_session",
    )


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    domain: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=DomainStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    verification_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    mailboxes: Mapped[list["Mailbox"]] = relationship(
        back_populates="domain",
    )


class Mailbox(Base):
    __tablename__ = "mailboxes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
    )

    tempmail_token: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    mailbox_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    guest_session_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "guest_sessions.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    domain_id: Mapped[int] = mapped_column(
        ForeignKey(
            "domains.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    country: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    country_code: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    user: Mapped["User | None"] = relationship(
        back_populates="mailboxes",
    )

    guest_session: Mapped["GuestSession | None"] = relationship(
        back_populates="mailboxes",
    )

    domain: Mapped["Domain"] = relationship(
        back_populates="mailboxes",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "email",
            name="uq_user_mailbox",
        ),
    )


class Activity(Base):
    __tablename__ = "activity"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    guest_session_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "guest_sessions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    event: Mapped[str] = mapped_column(
        String(100),
        index=True,
    )

    country: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    country_code: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    metadata_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )


class AnalyticsDaily(Base):
    __tablename__ = "analytics_daily"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    date: Mapped[datetime] = mapped_column(
        Date,
        unique=True,
        index=True,
    )

    registered_users: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    emails_generated: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    emails_received: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )