"""
Database engine, session factory, and the FastAPI Depends helper.

Supports both SQLite (local dev) and PostgreSQL (Supabase / any Postgres).
The active database is selected entirely through DATABASE_URL in .env —
no code change needed when switching environments.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from models import Base

# Load .env from project root. Shell variables take precedence.
load_dotenv()

# ---------------------------------------------------------------------------
# Read DATABASE_URL
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "sqlite:///./capstone.db",   # safe default — works with zero config
)

# ---------------------------------------------------------------------------
# Engine config — differs between SQLite and PostgreSQL
# ---------------------------------------------------------------------------
is_sqlite   = DATABASE_URL.startswith("sqlite")
is_postgres = DATABASE_URL.startswith("postgresql")

if is_sqlite:
    # SQLite: allow the same connection across threads (required by FastAPI)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )

elif is_postgres:
    # PostgreSQL / Supabase Transaction Pooler:
    # - NullPool: each request gets a fresh connection from the pooler.
    #   Required for Supabase's transaction-mode pooler (port 5432) because
    #   it does not support persistent server-side prepared statements.
    # - pool_pre_ping: test the connection before use to catch stale sockets.
    from sqlalchemy.pool import NullPool
    engine = create_engine(
        DATABASE_URL,
        poolclass=NullPool,
        pool_pre_ping=True,
        echo=False,
    )

else:
    # Generic fallback for any other DB URL
    engine = create_engine(DATABASE_URL, echo=False)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

# ---------------------------------------------------------------------------
# Table creation (called once at startup via lifespan in main.py)
# ---------------------------------------------------------------------------
def create_tables() -> None:
    """Create all tables that do not yet exist. Safe to call on every startup."""
    Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# FastAPI dependency — injected into every endpoint via Depends(get_db)
# ---------------------------------------------------------------------------
def get_db():
    """
    Yield a SQLAlchemy Session for one request, then close it.
    The finally block guarantees the session is released even on errors.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
