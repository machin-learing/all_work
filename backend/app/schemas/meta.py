from pydantic import BaseModel, ConfigDict


class OptionResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str

    model_config = ConfigDict(from_attributes=True)
