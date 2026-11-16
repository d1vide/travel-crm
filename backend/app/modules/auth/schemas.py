from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.auth.models import Role


class Dto(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, hide_input_in_errors=True)


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


class AuthResult(Dto):
    access_token: str = Field(min_length=1, repr=False)
    user: UserDto
