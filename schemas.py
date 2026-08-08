"""
Pydantic v2 request / response schemas.

Design notes
------------
* TaskCreate / TaskUpdate carry a priority field constrained to the closed
  set {"low", "medium", "high"} via a Literal type + Field.
* A field_validator on 'title' rejects blank strings (empty or whitespace-only)
  after stripping, fulfilling the "at least one custom validator" requirement.
* All *Response schemas include the generated id so callers can use it in
  subsequent requests.
* TaskStatusCount and ProjectStatsResponse are used by the statistics endpoint;
  they carry only the counts — no task rows — because the aggregation happens
  at the SQL level.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ─────────────────────────────────────────────────────────────────────────────
# Shared type aliases
# ─────────────────────────────────────────────────────────────────────────────

PriorityT = Literal["low", "medium", "high"]
StatusT   = Literal["todo", "in_progress", "done"]


# =============================================================================
# User schemas
# =============================================================================

class UserCreate(BaseModel):
    name:  str = Field(..., min_length=1, max_length=120, description="Display name")
    email: str = Field(..., max_length=254, description="Unique e-mail address")

    @field_validator("name", "email", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("Field must not be blank")
        return v


class UserUpdate(BaseModel):
    name:  Optional[str] = Field(None, min_length=1, max_length=120)
    email: Optional[str] = Field(None, max_length=254)

    @field_validator("name", "email", mode="before")
    @classmethod
    def strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Field must not be blank")
        return v


class UserResponse(BaseModel):
    id:         int
    name:       str
    email:      str
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# Project schemas
# =============================================================================

class ProjectCreate(BaseModel):
    name:        str            = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    owner_id:    int            = Field(..., gt=0)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("Project name must not be blank")
        return v


class ProjectUpdate(BaseModel):
    name:        Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Project name must not be blank")
        return v


class ProjectResponse(BaseModel):
    id:          int
    name:        str
    description: Optional[str]
    owner_id:    int

    model_config = {"from_attributes": True}


# =============================================================================
# Task schemas
# =============================================================================

class TaskCreate(BaseModel):
    title:       str            = Field(..., min_length=1, max_length=300)
    description: Optional[str] = Field(None, max_length=2000)

    # Closed set — exactly three allowed values, matching the AI parser output
    priority: PriorityT = Field(
        "medium",
        description="Task priority: low | medium | high",
    )
    status:   StatusT   = Field(
        "todo",
        description="Task status: todo | in_progress | done",
    )

    # Stores raw text — a parsed phrase like 'next friday' is equally valid
    due_date:   Optional[str] = Field(
        None,
        max_length=100,
        description="Due date as free text, e.g. '2025-12-31' or 'next friday'",
    )
    project_id: int = Field(..., gt=0)

    # ── Custom validator: reject blank title after trimming ──────────────────
    @field_validator("title", mode="before")
    @classmethod
    def title_must_not_be_blank(cls, v: str) -> str:
        """Strip surrounding whitespace, then reject an empty string."""
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("Task title must not be blank or whitespace-only")
        return v

    @field_validator("description", "due_date", mode="before")
    @classmethod
    def normalise_optional_strings(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = v.strip() or None
        return v


class TaskUpdate(BaseModel):
    title:       Optional[str]      = Field(None, max_length=300)
    description: Optional[str]      = Field(None, max_length=2000)
    priority:    Optional[PriorityT] = None
    status:      Optional[StatusT]   = None
    due_date:    Optional[str]       = Field(None, max_length=100)

    @field_validator("title", mode="before")
    @classmethod
    def title_must_not_be_blank(cls, v: Optional[str]) -> Optional[str]:
        """If a title is supplied, it must not be blank after stripping."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Task title must not be blank or whitespace-only")
        return v

    @field_validator("description", "due_date", mode="before")
    @classmethod
    def normalise_optional_strings(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = v.strip() or None
        return v


class TaskResponse(BaseModel):
    id:          int
    title:       str
    description: Optional[str]
    priority:    str
    status:      str
    due_date:    Optional[str]
    project_id:  int
    created_at:  datetime

    model_config = {"from_attributes": True}


# =============================================================================
# Quick-add schema  (used by POST /tasks/quick-add)
# =============================================================================

class QuickAddRequest(BaseModel):
    """
    Request body for POST /tasks/quick-add.

    The endpoint passes *description* through the mock (or real) NLP parser to
    derive title, priority, and due_date_hint, then creates a task row in the
    database belonging to *project_id*.
    """
    description: str = Field(
        ...,
        min_length=1,
        description="Free-text description of the task to create",
    )
    project_id: int = Field(
        ...,
        gt=0,
        description="ID of the project this task belongs to",
    )

    @field_validator("description", mode="before")
    @classmethod
    def description_must_not_be_blank(cls, v: str) -> str:
        """Reject a description that is empty or whitespace-only after stripping."""
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("description must not be blank or whitespace-only")
        return v


# =============================================================================
# Statistics schemas  (used by the per-project stats endpoint)
# =============================================================================

class TaskStatusCount(BaseModel):
    """Count of tasks in a single status bucket."""
    status: str
    count:  int


class ProjectStatsResponse(BaseModel):
    """Aggregated task statistics for one project."""
    project_id:   int
    project_name: str
    total_tasks:  int
    by_status:    list[TaskStatusCount]
