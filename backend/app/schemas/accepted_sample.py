from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AcceptedSampleCreate(BaseModel):
    transfer_id: int


class AcceptedSampleReview(BaseModel):
    review_status: str


class AcceptedSampleResponse(BaseModel):
    id: int
    transfer_id: int
    source_text: str
    rewritten_text: str
    review_status: str
    created_at: datetime
    role_code: str
    role_name: str
    model_code: str
    model_name: str
    username: str

    model_config = ConfigDict(from_attributes=True)
