from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TransferRecord(Base):
    __tablename__ = "transfer_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("role_options.id"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("model_options.id"), index=True)
    source_text: Mapped[str] = mapped_column(Text)
    rewritten_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="success")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="transfer_records")
    role = relationship("RoleOption", back_populates="transfer_records")
    model = relationship("ModelOption", back_populates="transfer_records")
