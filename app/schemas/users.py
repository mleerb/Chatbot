from pydantic import BaseModel, Field


class UserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class UserResponse(BaseModel):
    id: int
    name: str
