from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from app.core.schemas import Dto
from app.modules.auth.models import Role


class LoginInput(Dto):
    email: EmailStr
    password: str = Field(min_length=1, repr=False)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class UserDto(Dto):
    id: UUID
    full_name: str = Field(min_length=1)
    role: Role


class UserProfileDto(UserDto):
    email: str = Field(max_length=320)
    department: str | None = Field(max_length=255)
    position: str | None = Field(max_length=255)
    work_phone: str | None = Field(max_length=64)


class AuthResult(Dto):
    access_token: str = Field(min_length=1, repr=False)
    user: UserDto
