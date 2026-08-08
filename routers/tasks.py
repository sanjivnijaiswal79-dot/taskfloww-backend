"""
Tasks router — full CRUD endpoints plus sort, search, and quick-add.

Routes
------
POST   /tasks/                                → 201  create a task
GET    /tasks/                                → 200  list tasks (optional ?project_id, ?sort)
GET    /tasks/search                          → 200 | 404  exact-title search
POST   /tasks/quick-add                       → 201  NLP-assisted quick task creation
GET    /tasks/{id}                            → 200 | 404
PUT    /tasks/{id}                            → 200 | 404 | 422
DELETE /tasks/{id}                            → 204 | 404

Sorting (GET /tasks?sort=priority or ?sort=due_date)
------------------------------------------------------
Tasks are fetched from the database into Python dictionaries and then
ordered by our hand-rolled insertion_sort — never by SQL ORDER BY or
Python's built-in sorted()/list.sort().

Priority is mapped to an integer rank so the sort is numerically
comparable:
    low → 1   medium → 2   high → 3

When sort=due_date the raw due_date string is used as-is as the sort key
(lexicographic ordering, which works correctly for ISO-8601 dates).

Search (GET /tasks/search?title=<exact text>&algo=binary|linear)
---------------------------------------------------------------
Builds an in-memory index of {"id": ..., "title": ...} dicts from the
real tasks in the database, then locates the exact-title match using:
  • binary_search  (default) — sorts the index by title with insertion_sort
                               first, then searches in O(log n)
  • linear_search             — scans the unsorted index in O(n)

Returns the full matching task (200) or 404 if no task has that exact title.

Quick-add (POST /tasks/quick-add)
----------------------------------
Accepts {"description": "<free text>", "project_id": <int>}.
Builds a role-based prompt (system + user messages), passes it through the
deterministic mock parser (or optionally a real LLM when USE_REAL_LLM=1 is
set), validates the result against the Pydantic response model, persists a
row to the tasks table, and returns the created task (201).

All handlers inject the shared DB session via Depends(get_db).
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Project, Task
from ..schemas import QuickAddRequest, TaskCreate, TaskResponse, TaskUpdate
from ..algorithms import binary_search, insertion_sort, linear_search
from ..parser import build_prompt, parse_quick_add

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ─── constants ───────────────────────────────────────────────────────────────

# Maps the three priority strings to comparable integer ranks.
# Higher numbers = higher priority so that sorting ascending gives low→high.
PRIORITY_RANK: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
}

# Accepted values for the ?sort query parameter
SORT_KEYS = {"priority", "due_date"}

# Accepted values for the ?algo query parameter on the search endpoint
ALGO_CHOICES = {"binary", "linear"}


# ─── helpers ─────────────────────────────────────────────────────────────────

def _get_or_404(task_id: int, db: Session) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )
    return task


def _task_to_dict(task: Task) -> dict:
    """Convert a Task ORM row to a plain dict for in-memory algorithm use."""
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "priority_rank": PRIORITY_RANK.get(task.priority, 0),
        "status": task.status,
        "due_date": task.due_date or "",   # treat NULL as "" for sorting
        "project_id": task.project_id,
        "created_at": task.created_at,
    }


# ─── endpoints ───────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task",
)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> Task:
    # Validate that the referenced project exists → 404 if not
    if not db.get(Project, payload.project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {payload.project_id} not found",
        )

    task = Task(
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        status=payload.status,
        due_date=payload.due_date,
        project_id=payload.project_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get(
    "/search",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Search tasks by exact title using binary_search or linear_search",
)
def search_tasks(
    title: str = Query(..., description="Exact title text to search for"),
    algo: str = Query(
        "binary",
        description="Search algorithm: 'binary' (default) or 'linear'",
    ),
    db: Session = Depends(get_db),
) -> Task:
    """
    Locate a task by exact title.

    Implementation
    --------------
    1. Fetch all tasks from the database as Python dicts (no SQL WHERE clause).
    2. Build a lightweight index list of {"id": ..., "title": ...} dicts.
    3a. algo=binary  — sort the index by title using insertion_sort, then
                       call binary_search to find the title in O(log n).
    3b. algo=linear  — call linear_search over the unsorted index in O(n).
    4. If found, fetch the full Task row by its id and return it (200).
       If not found, raise 404.

    The search never uses SQL LIKE/WHERE or Python's built-in sort.
    """
    if algo not in ALGO_CHOICES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"algo must be one of {sorted(ALGO_CHOICES)}",
        )

    # Step 1 & 2: build in-memory index from all database tasks
    all_tasks = db.query(Task).all()
    index = [{"id": t.id, "title": t.title} for t in all_tasks]

    if algo == "binary":
        # Sort the index by title first (required for binary_search to be correct)
        insertion_sort(index, "title")
        found_idx = binary_search(index, title, "title")
    else:
        # linear_search works on the unsorted index directly
        found_idx = linear_search(index, title, "title")

    if found_idx == -1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No task with title '{title}' found",
        )

    # Retrieve the full task row from the database by its id
    task_id = index[found_idx]["id"]
    return _get_or_404(task_id, db)


@router.get(
    "/",
    response_model=list[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="List tasks, optionally filtered by project and/or sorted by field",
)
def list_tasks(
    project_id: int | None = Query(None, description="Filter by project ID"),
    sort: str | None = Query(
        None,
        description="Sort field: 'priority' (low→high) or 'due_date' (ascending). "
                    "Ordering is performed by insertion_sort — not SQL ORDER BY.",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    """
    List tasks with optional project filter and hand-rolled sort.

    When *sort* is provided the endpoint:
    1. Fetches matching task rows from the database.
    2. Converts each row to a plain dict.
    3. Calls insertion_sort on that dict list using a numeric key:
       - sort=priority  → sorts by "priority_rank" (1=low, 2=medium, 3=high)
       - sort=due_date  → sorts by "due_date" (lexicographic / ISO-8601)
    4. Returns the sorted list.

    The ordering the client sees is produced entirely by insertion_sort —
    there is no ORDER BY in the SQL query, and Python's sorted()/list.sort()
    are never called.
    """
    if sort is not None and sort not in SORT_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"sort must be one of {sorted(SORT_KEYS)}",
        )

    q = db.query(Task)
    if project_id is not None:
        q = q.filter(Task.project_id == project_id)
    tasks = q.offset(skip).limit(limit).all()

    if sort is None:
        # No sort requested — return ORM objects directly (FastAPI serialises them)
        return tasks

    # Convert to dicts so insertion_sort can operate in place
    records = [_task_to_dict(t) for t in tasks]

    # Choose the sort key: priority uses the integer rank; due_date sorts lexicographically
    sort_key = "priority_rank" if sort == "priority" else "due_date"

    # Hand-rolled sort — never sorted() or list.sort()
    insertion_sort(records, sort_key)

    return records


# ─── quick-add endpoint ───────────────────────────────────────────────────────

def _call_parser(description: str) -> dict:
    """
    Choose between the mock parser and an optional real LLM call.

    The environment variable USE_REAL_LLM controls which path is taken:
      • unset or "0" → use the deterministic mock (default, no API key needed)
      • "1"          → attempt a real LLM call; fall back to mock on any error

    This function always returns a dict with the keys:
        {"title": str, "priority": str, "due_date_hint": str | None}
    """
    use_real = os.environ.get("USE_REAL_LLM", "0").strip() == "1"

    if use_real:
        # Optional real-LLM path — only attempted when the flag is set.
        # Falls back to the mock automatically if the key is missing or the
        # call fails, so the endpoint never requires a paid service.
        try:
            import openai  # type: ignore
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set — falling back to mock")

            client = openai.OpenAI(api_key=api_key)
            messages = build_prompt(description)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0,
                max_tokens=120,
            )
            import json as _json
            raw = response.choices[0].message.content or ""
            parsed = _json.loads(raw)
            # Normalise the key name the model might use
            if "due_date_hint" not in parsed and "due_date" in parsed:
                parsed["due_date_hint"] = parsed.pop("due_date")
            return parsed
        except Exception:
            # Any failure (missing key, network error, bad JSON) → fall back
            pass

    # Default: deterministic mock — zero network calls, zero API keys.
    return parse_quick_add(description)


@router.post(
    "/quick-add",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task from a free-text description using the NLP parser",
)
def quick_add_task(
    payload: QuickAddRequest,
    db: Session = Depends(get_db),
) -> Task:
    """
    Parse a free-text description into a structured task and persist it.

    Steps
    -----
    1. Validate the request body via QuickAddRequest (description non-blank,
       project_id > 0).  Pydantic raises 422 before this handler runs if the
       body is malformed.
    2. Verify the project exists — 404 if not.
    3. Build the role-based prompt (system + user messages) to make the
       prompt structure explicit, then call the parser.
    4. Validate the parser output against TaskCreate before touching the DB —
       returns 422 if the parser produced invalid values (should never happen
       with the mock, but guards against a misbehaving real LLM).
    5. Persist the task and return it (201).

    The endpoint works correctly with no API key set anywhere — the mock is
    the default parser and requires zero network calls.
    """
    # Step 2: project must exist
    if not db.get(Project, payload.project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {payload.project_id} not found",
        )

    # Step 3: build prompt (documents the LLM contract) then run the parser
    _prompt = build_prompt(payload.description)   # noqa: F841 — kept for clarity
    parsed = _call_parser(payload.description)

    # Step 4: validate parser output — raises 422 on invalid values
    try:
        task_create = TaskCreate(
            title       = parsed["title"],
            description = payload.description,
            priority    = parsed["priority"],
            status      = "todo",
            due_date    = parsed.get("due_date_hint"),
            project_id  = payload.project_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Parser produced invalid task fields: {exc}",
        )

    # Step 5: persist
    task = Task(
        title       = task_create.title,
        description = task_create.description,
        priority    = task_create.priority,
        status      = task_create.status,
        due_date    = task_create.due_date,
        project_id  = task_create.project_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a task by ID",
)
def get_task(task_id: int, db: Session = Depends(get_db)) -> Task:
    return _get_or_404(task_id, db)


@router.put(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a task (partial update — send only the fields that change)",
)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
) -> Task:
    task = _get_or_404(task_id, db)

    # Apply only the fields the caller sent (exclude_unset → partial PATCH-style)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)
    return task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
)
def delete_task(task_id: int, db: Session = Depends(get_db)) -> None:
    task = _get_or_404(task_id, db)
    db.delete(task)
    db.commit()
