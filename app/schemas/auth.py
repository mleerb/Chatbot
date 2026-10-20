from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(LoginRequest):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)


class AccountResponse(BaseModel):
    id: int
    name: str
    email: str


class AuthResponse(BaseModel):
    user: AccountResponse | None
    guest: bool = False
    guest_token: str | None = None
