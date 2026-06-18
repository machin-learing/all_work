from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AcceptedSample(Base):
    __tablename__ = "accepted_samples"
    __table_args__ = (
        UniqueConstraint("transfer_id", "user_id", name="uq_accepted_transfer_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    transfer_id: Mapped[int] = mapped_column(
        ForeignKey("transfer_records.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role_code: Mapped[str] = mapped_column(String(50), index=True)
    role_name: Mapped[str] = mapped_column(String(50))
    model_code: Mapped[str] = mapped_column(String(50), index=True)
    model_name: Mapped[str] = mapped_column(String(50))
    source_text: Mapped[str] = mapped_column(Text)
    rewritten_text: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    transfer = relationship("TransferRecord")
    user = relationship("User")
