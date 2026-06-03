"""SQLite async database setup via SQLAlchemy."""

import logging
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

import os as _os
_DATA_DIR = _os.getenv("DATA_DIR", str(Path(__file__).resolve().parent.parent))
DB_PATH = Path(_DATA_DIR) / "argus.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class AOIRow(Base):
    """Persistent AOI record."""

    __tablename__ = "aois"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    min_lon = Column(Float, nullable=False)
    min_lat = Column(Float, nullable=False)
    max_lon = Column(Float, nullable=False)
    max_lat = Column(Float, nullable=False)
    domain = Column(String, nullable=False)
    terrain_type = Column(String, nullable=True)
    device_id = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False)
    revisit_hours = Column(Integer, default=24)


class ContactRow(Base):
    """Persistent single-source contact record."""

    __tablename__ = "contacts"

    id = Column(String, primary_key=True)
    aoi_id = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    source = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    detection_type = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    description = Column(Text, nullable=False)
    raw_evidence = Column(Text, default="{}")
    fused = Column(Boolean, default=False)
    threat_level = Column(String, nullable=True)


class FusedContactRow(Base):
    """Persistent fused contact record."""

    __tablename__ = "fused_contacts"

    id = Column(String, primary_key=True)
    aoi_id = Column(String, nullable=False)
    constituent_contacts = Column(Text, nullable=False)
    sources = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    detection_types = Column(Text, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    threat_level = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    simulation_run = Column(Boolean, default=False)

    # Temporal intelligence
    track_id = Column(String, nullable=True)
    first_seen = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    observation_count = Column(Integer, default=1)
    lifecycle = Column(String, default="new")
    confidence_delta = Column(Float, default=0.0)
    persistence_score = Column(Float, default=0.0)


class IntelReportRow(Base):
    """Persistent intelligence report record."""

    __tablename__ = "intel_reports"

    id = Column(String, primary_key=True)
    aoi_id = Column(String, nullable=False)
    generated_at = Column(DateTime, nullable=False)
    fused_contacts = Column(Text, nullable=False)
    threat_assessment = Column(Text, nullable=False)
    key_findings = Column(Text, nullable=False)
    recommended_actions = Column(Text, nullable=False)
    pdf_path = Column(String, nullable=True)


# Columns added after the initial schema — applied to existing DBs on startup.
_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "aois": [
        ("terrain_type", "VARCHAR"),
        ("device_id", "VARCHAR"),
    ],
    "fused_contacts": [
        ("track_id", "VARCHAR"),
        ("first_seen", "DATETIME"),
        ("last_seen", "DATETIME"),
        ("observation_count", "INTEGER DEFAULT 1"),
        ("lifecycle", "VARCHAR DEFAULT 'new'"),
        ("confidence_delta", "FLOAT DEFAULT 0.0"),
        ("persistence_score", "FLOAT DEFAULT 0.0"),
    ],
}


def _apply_migrations(conn) -> None:
    """Idempotently add any missing columns to existing tables (SQLite)."""
    for table, columns in _MIGRATIONS.items():
        existing = {
            row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
        }
        for name, ddl in columns:
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                logger.info("Migration: added %s.%s", table, name)


async def init_db() -> None:
    """Create all tables if they don't exist, then apply column migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_migrations)
    logger.info("Database initialized at %s", DB_PATH)


async def get_db() -> AsyncSession:
    """Yield an async database session."""
    async with async_session() as session:
        yield session
