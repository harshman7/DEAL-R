"""SQLAlchemy models for event store."""

from datetime import datetime

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


class EventModel(Base):
    """Event stored in database."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hand_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_data: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=lambda: int(datetime.now().timestamp())
    )


class HandSnapshotModel(Base):
    """Optional snapshot of hand state."""

    __tablename__ = "hand_snapshots"

    hand_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state_data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=lambda: int(datetime.now().timestamp())
    )


class CommandModel(Base):
    """Command tracking for idempotency."""

    __tablename__ = "commands"

    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    hand_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    command_type: Mapped[str] = mapped_column(String(100), nullable=False)
    command_data: Mapped[str] = mapped_column(Text, nullable=False)
    result_events: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=lambda: int(datetime.now().timestamp())
    )


def init_db(engine: Engine) -> None:
    """Initialize database tables."""
    Base.metadata.create_all(engine)
