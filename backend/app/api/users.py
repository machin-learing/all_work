from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserResponse


router = APIRouter()


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("", response_model=list[UserResponse])
def list_users(
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at.desc())).all())
