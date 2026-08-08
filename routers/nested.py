"""
Nested resource routes.

Routes
------
GET  /users/{user_id}/projects      → 200 | 404   list all projects owned by user
GET  /projects/{project_id}/tasks   → 200 | 404   list all tasks for a project

These are read-only convenience endpoints that follow the natural hierarchy:
  User → Projects → Tasks
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Project, Task, User
from ..schemas import ProjectResponse, TaskResponse

router = APIRouter(tags=["nested"])


# ─── GET /users/{user_id}/projects ───────────────────────────────────────────

@router.get(
    "/users/{user_id}/projects",
    response_model=list[ProjectResponse],
    status_code=status.HTTP_200_OK,
    summary="List all projects owned by a user",
)
def get_user_projects(
    user_id: int,
    db: Session = Depends(get_db),
) -> list[Project]:
    """Return every project whose owner_id matches *user_id*.

    Raises **404** if no user with the given id exists.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    return user.projects


# ─── GET /projects/{project_id}/tasks ────────────────────────────────────────

@router.get(
    "/projects/{project_id}/tasks",
    response_model=list[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="List all tasks belonging to a project",
)
def get_project_tasks(
    project_id: int,
    db: Session = Depends(get_db),
) -> list[Task]:
    """Return every task whose project_id matches *project_id*.

    Raises **404** if no project with the given id exists.
    """
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project.tasks
