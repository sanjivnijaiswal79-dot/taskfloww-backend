"""
Projects router — CRUD endpoints + per-project task statistics.

Routes
------
POST   /projects/                   → 201  create a project
GET    /projects/                   → 200  list all projects
GET    /projects/{id}               → 200 | 404
PUT    /projects/{id}               → 200 | 404 | 422
DELETE /projects/{id}               → 204 | 404
GET    /projects/{id}/stats         → 200 | 404  per-project task statistics

The stats endpoint uses a SQLAlchemy GROUP BY aggregate — no Python-level
counting over full task rows.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Project, Task, User
from schemas import (
    ProjectCreate,
    ProjectResponse,
    ProjectStatsResponse,
    ProjectUpdate,
    TaskStatusCount,
)

router = APIRouter(prefix="/projects", tags=["projects"])


# ─── helpers ─────────────────────────────────────────────────────────────────

def _get_or_404(project_id: int, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project


# ─── endpoints ───────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    # Validate that the owner exists
    if not db.get(User, payload.owner_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owner user {payload.owner_id} not found",
        )
    project = Project(
        name=payload.name,
        description=payload.description,
        owner_id=payload.owner_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get(
    "/",
    response_model=list[ProjectResponse],
    status_code=status.HTTP_200_OK,
    summary="List all projects",
)
def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[Project]:
    return db.query(Project).offset(skip).limit(limit).all()


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a project by ID",
)
def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    return _get_or_404(project_id, db)


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a project",
)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
) -> Project:
    project = _get_or_404(project_id, db)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    return project


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
)
def delete_project(project_id: int, db: Session = Depends(get_db)) -> None:
    project = _get_or_404(project_id, db)
    db.delete(project)
    db.commit()


# ─── statistics endpoint ─────────────────────────────────────────────────────

@router.get(
    "/{project_id}/stats",
    response_model=ProjectStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Per-project task statistics (aggregated in SQL)",
)
def project_stats(project_id: int, db: Session = Depends(get_db)) -> ProjectStatsResponse:
    """
    Returns the total task count and a count per status for the given project.

    The aggregation is performed entirely in SQL via COUNT + GROUP BY — no
    Python-level iteration over all task rows.

    SQL produced (roughly):
        SELECT   tasks.status, COUNT(tasks.id) AS count
        FROM     projects
        JOIN     tasks ON tasks.project_id = projects.id
        WHERE    projects.id = :project_id
        GROUP BY tasks.status
    """
    project = _get_or_404(project_id, db)

    # One DB round-trip: SELECT status, COUNT(*) FROM tasks WHERE project_id=?
    # GROUP BY status
    rows = (
        db.query(Task.status, func.count(Task.id).label("count"))
        .filter(Task.project_id == project_id)
        .group_by(Task.status)
        .all()
    )

    # Build per-status buckets and compute total
    by_status = [TaskStatusCount(status=row.status, count=row.count) for row in rows]
    total = sum(b.count for b in by_status)

    return ProjectStatsResponse(
        project_id=project.id,
        project_name=project.name,
        total_tasks=total,
        by_status=by_status,
    )
