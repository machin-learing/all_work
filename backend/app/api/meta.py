from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.model_option import ModelOption
from app.models.role_option import RoleOption
from app.models.user import User
from app.schemas.meta import OptionResponse


router = APIRouter()


@router.get("/roles", response_model=list[OptionResponse])
def list_roles(
    _: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[RoleOption]:
    return list(db.scalars(select(RoleOption).order_by(RoleOption.id.asc())).all())


@router.get("/models", response_model=list[OptionResponse])
def list_models(
    _: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ModelOption]:
    return list(db.scalars(select(ModelOption).order_by(ModelOption.id.asc())).all())
