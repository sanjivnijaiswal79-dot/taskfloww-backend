"""
Users router — CRUD endpoints.

Routes
------
POST   /users/           → 201  create a user
GET    /users/           → 200  list all users
GET    /users/{id}       → 200 | 404
PUT    /users/{id}       → 200 | 404 | 422
DELETE /users/{id}       → 204 | 404

The `db` session is injected via Depends(get_db) — the same dependency
reused in every handler rather than duplicated.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from ..models import User
from ..schemas import UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


# ─── helpers ─────────────────────────────────────────────────────────────────

def _get_or_404(user_id: int, db: Session) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    return user


# ─── endpoints ───────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    user = User(name=payload.name, email=payload.email)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{payload.email}' is already registered",
        )
    db.refresh(user)
    return user


@router.get(
    "/",
    response_model=list[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="List all users",
)
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[User]:
    return db.query(User).offset(skip).limit(limit).all()


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a user by ID",
)
def get_user(user_id: int, db: Session = Depends(get_db)) -> User:
    return _get_or_404(user_id, db)


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a user",
)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
) -> User:
    user = _get_or_404(user_id, db)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already in use by another account",
        )
    db.refresh(user)
    return user


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user",
)
def delete_user(user_id: int, db: Session = Depends(get_db)) -> None:
    user = _get_or_404(user_id, db)
    db.delete(user)
    db.commit()
