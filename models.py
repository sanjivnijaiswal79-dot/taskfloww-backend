"""
SQLAlchemy ORM models.

Schema:
  users       – id, name, email (UNIQUE, NOT NULL), created_at
  projects    – id, name (NOT NULL), description, owner_id (FK → users.id)
  tasks       – id, title (NOT NULL), description, status, priority (low/medium/high),
                due_date (nullable TEXT), project_id (FK → projects.id), created_at

Relationships (both sides use back_populates):
  User.projects  ↔  Project.owner
  Project.tasks  ↔  Task.project
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enumerations stored in the DB
# ---------------------------------------------------------------------------

PRIORITY_VALUES = ("low", "medium", "high")
STATUS_VALUES   = ("todo", "in_progress", "done")


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(120), nullable=False)
    email      = Column(String(254), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # One user → many projects
    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    owner_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Many-to-one back to User
    owner = relationship("User", back_populates="projects")

    # One project → many tasks
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

class Task(Base):
    __tablename__ = "tasks"

    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)

    # Restricted to the same three values the AI parser produces (Section 3)
    priority    = Column(
        Enum(*PRIORITY_VALUES, name="priority_enum"),
        nullable=False,
        default="medium",
    )

    # Restricted to the task lifecycle states
    status      = Column(
        Enum(*STATUS_VALUES, name="status_enum"),
        nullable=False,
        default="todo",
    )

    # Intentionally TEXT so both "2025-12-31" and "next friday" are valid values
    due_date    = Column(String(100), nullable=True)

    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    project_id  = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # Many-to-one back to Project
    project = relationship("Project", back_populates="tasks")

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title!r} priority={self.priority}>"
