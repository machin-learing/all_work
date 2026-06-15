from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TransferCreate(BaseModel):
    source_text: str = Field(min_length=1, max_length=2000)
    role_code: str
    model_code: str


class TransferResponse(BaseModel):
    id: int
    source_text: str
    rewritten_text: str
    status: str
    created_at: datetime
    role_name: str
    role_code: str
    model_name: str
    model_code: str
    username: str

    model_config = ConfigDict(from_attributes=True)
