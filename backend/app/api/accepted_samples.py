from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.accepted_sample import AcceptedSample
from app.models.transfer_record import TransferRecord
from app.models.user import User
from app.schemas.accepted_sample import AcceptedSampleCreate, AcceptedSampleResponse


router = APIRouter()


def _to_response(sample: AcceptedSample) -> AcceptedSampleResponse:
    return AcceptedSampleResponse(
        id=sample.id,
        transfer_id=sample.transfer_id,
        source_text=sample.source_text,
        rewritten_text=sample.rewritten_text,
        review_status=sample.review_status,
        created_at=sample.created_at,
        role_code=sample.role_code,
        role_name=sample.role_name,
        model_code=sample.model_code,
        model_name=sample.model_name,
        username=sample.user.username,
    )


def _get_with_user(db: Session, sample_id: int) -> AcceptedSample | None:
    return db.scalar(
        select(AcceptedSample)
        .options(joinedload(AcceptedSample.user))
        .where(AcceptedSample.id == sample_id)
    )


@router.post("", response_model=AcceptedSampleResponse)
def create_accepted_sample(
    payload: AcceptedSampleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AcceptedSampleResponse:
    stmt = (
        select(TransferRecord)
        .options(
            joinedload(TransferRecord.user),
            joinedload(TransferRecord.role),
            joinedload(TransferRecord.model),
        )
        .where(TransferRecord.id == payload.transfer_id)
    )
    record = db.scalar(stmt)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="改写记录不存在"
        )
    if not current_user.is_admin and record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="不能采纳其他用户的记录"
        )

    sample = AcceptedSample(
        transfer_id=record.id,
        user_id=current_user.id,
        role_code=record.role.code,
        role_name=record.role.name,
        model_code=record.model.code,
        model_name=record.model.name,
        source_text=record.source_text,
        rewritten_text=record.rewritten_text,
        review_status="pending",
    )
    db.add(sample)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(AcceptedSample)
            .options(joinedload(AcceptedSample.user))
            .where(
                AcceptedSample.transfer_id == record.id,
                AcceptedSample.user_id == current_user.id,
            )
        )
        if existing:
            return _to_response(existing)
        raise

    sample_with_user = _get_with_user(db, sample.id)
    if not sample_with_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="采纳样本保存失败",
        )
    return _to_response(sample_with_user)


@router.get("", response_model=list[AcceptedSampleResponse])
def list_accepted_samples(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AcceptedSampleResponse]:
    stmt = (
        select(AcceptedSample)
        .options(joinedload(AcceptedSample.user))
        .order_by(AcceptedSample.created_at.desc())
    )
    if not current_user.is_admin:
        stmt = stmt.where(AcceptedSample.user_id == current_user.id)
    samples = list(db.scalars(stmt).all())
    return [_to_response(sample) for sample in samples]
