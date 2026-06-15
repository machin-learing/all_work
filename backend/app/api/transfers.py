from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.model_option import ModelOption
from app.models.role_option import RoleOption
from app.models.transfer_record import TransferRecord
from app.models.user import User
from app.schemas.transfer import TransferCreate, TransferResponse
from app.services.model_runner import rewrite_text


router = APIRouter()


def to_response(record: TransferRecord) -> TransferResponse:
    return TransferResponse(
        id=record.id,
        source_text=record.source_text,
        rewritten_text=record.rewritten_text,
        status=record.status,
        created_at=record.created_at,
        role_name=record.role.name,
        role_code=record.role.code,
        model_name=record.model.name,
        model_code=record.model.code,
        username=record.user.username,
    )


@router.post("", response_model=TransferResponse)
def create_transfer(
    payload: TransferCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransferResponse:
    role = db.scalar(select(RoleOption).where(RoleOption.code == payload.role_code))
    model = db.scalar(select(ModelOption).where(ModelOption.code == payload.model_code))
    if not role or not model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="角色或模型配置不存在"
        )

    rewritten_text = rewrite_text(
        source_text=payload.source_text,
        role_code=role.code,
        model_code=model.code,
    )
    record = TransferRecord(
        user_id=current_user.id,
        role_id=role.id,
        model_id=model.id,
        source_text=payload.source_text,
        rewritten_text=rewritten_text,
        status="success",
    )
    db.add(record)
    db.commit()
    record = db.scalar(
        select(TransferRecord)
        .options(
            joinedload(TransferRecord.user),
            joinedload(TransferRecord.role),
            joinedload(TransferRecord.model),
        )
        .where(TransferRecord.id == record.id)
    )
    return to_response(record)


@router.get("", response_model=list[TransferResponse])
def list_transfers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TransferResponse]:
    stmt = (
        select(TransferRecord)
        .options(
            joinedload(TransferRecord.user),
            joinedload(TransferRecord.role),
            joinedload(TransferRecord.model),
        )
        .order_by(TransferRecord.created_at.desc())
    )
    if not current_user.is_admin:
        stmt = stmt.where(TransferRecord.user_id == current_user.id)
    records = list(db.scalars(stmt).all())
    return [to_response(record) for record in records]
