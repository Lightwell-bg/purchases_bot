"""ORM-модели."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.database.types import Money, TZDateTime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class PurchaseStatus(StrEnum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    ORDERED = "ORDERED"
    SHIPPED = "SHIPPED"
    RECEIVED = "RECEIVED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ParticipantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


class RulesAction(StrEnum):
    CREATE_PURCHASE = "CREATE_PURCHASE"
    JOIN_PURCHASE = "JOIN_PURCHASE"


def _enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Храним enum строкой — так проще мигрировать и читать базу глазами."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda e: [item.value for item in e],
        length=20,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} tg={self.telegram_id}>"

    @property
    def display_name(self) -> str:
        """Как показывать пользователя в интерфейсе."""
        if self.username:
            return f"@{self.username}"
        parts = [p for p in (self.first_name, self.last_name) if p]
        return " ".join(parts) or f"id{self.telegram_id}"


class Purchase(Base, TimestampMixin):
    __tablename__ = "purchases"
    __table_args__ = (Index("ix_purchases_status_deadline", "status", "deadline"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    public_token: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    organizer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # Реальные ссылки маркетплейсов с трекинг-параметрами бывают под 2000 символов.
    product_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    variant_description: Mapped[str | None] = mapped_column(String(500))

    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="EUR", nullable=False)

    organizer_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    deadline: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    pickup_location: Mapped[str | None] = mapped_column(String(200))
    photo_file_id: Mapped[str | None] = mapped_column(String(300))

    status: Mapped[PurchaseStatus] = mapped_column(
        _enum(PurchaseStatus, "purchase_status"),
        default=PurchaseStatus.DRAFT,
        nullable=False,
        index=True,
    )

    group_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    group_message_id: Mapped[int | None] = mapped_column(Integer)

    organizer: Mapped[User] = relationship(lazy="selectin")
    participants: Mapped[list["Participant"]] = relationship(
        back_populates="purchase",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Purchase id={self.id} status={self.status}>"

    @property
    def active_participants(self) -> list["Participant"]:
        return [p for p in self.participants if p.status == ParticipantStatus.ACTIVE]


class Participant(Base, TimestampMixin):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("purchase_id", "user_id", name="uq_participant_purchase_user"),
        Index("ix_participants_purchase_status", "purchase_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    variant: Mapped[str | None] = mapped_column(String(300))
    comment: Mapped[str | None] = mapped_column(String(500))

    status: Mapped[ParticipantStatus] = mapped_column(
        _enum(ParticipantStatus, "participant_status"),
        default=ParticipantStatus.ACTIVE,
        nullable=False,
    )

    # Обратную сторону не грузим лениво: закупку всегда достаём явно,
    # иначе получаем рекурсивную загрузку purchase -> participants -> purchase.
    purchase: Mapped[Purchase] = relationship(back_populates="participants", lazy="raise")
    user: Mapped[User] = relationship(lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Participant id={self.id} purchase={self.purchase_id} qty={self.quantity}>"


class RulesAcceptance(Base):
    __tablename__ = "rules_acceptances"
    __table_args__ = (Index("ix_rules_user_action_version", "user_id", "action", "rules_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id", ondelete="SET NULL"))
    action: Mapped[RulesAction] = mapped_column(_enum(RulesAction, "rules_action"), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(20), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
