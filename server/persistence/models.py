"""SQLAlchemy models for event store."""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Column, Integer, String, Text
from sqlalchemy.orm import Session, declarative_base

Base = declarative_base()


class EventModel(Base):
    """Event stored in database."""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hand_id = Column(String(255), nullable=False, index=True)
    version = Column(Integer, nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    event_data = Column(Text, nullable=False)  # JSON serialized event
    timestamp = Column(BigInteger, nullable=False)  # Unix timestamp
    created_at = Column(BigInteger, nullable=False, default=lambda: int(datetime.now().timestamp()))


class HandSnapshotModel(Base):
    """Optional snapshot of hand state."""

    __tablename__ = "hand_snapshots"

    hand_id = Column(String(255), primary_key=True)
    version = Column(Integer, nullable=False)
    state_data = Column(Text, nullable=False)  # JSON serialized GameState
    created_at = Column(BigInteger, nullable=False, default=lambda: int(datetime.now().timestamp()))


class CommandModel(Base):
    """Command tracking for idempotency."""

    __tablename__ = "commands"

    idempotency_key = Column(String(255), primary_key=True)
    hand_id = Column(String(255), nullable=False, index=True)
    command_type = Column(String(100), nullable=False)
    command_data = Column(Text, nullable=False)  # JSON serialized command
    result_events = Column(Text, nullable=True)  # JSON serialized events
    created_at = Column(BigInteger, nullable=False, default=lambda: int(datetime.now().timestamp()))


def init_db(engine):
    """Initialize database tables."""
    Base.metadata.create_all(engine)

