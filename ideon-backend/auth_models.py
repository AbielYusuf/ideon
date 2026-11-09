"""Request/response models for Ideon authentication."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from auth import validate_email, validate_password, validate_username


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def username_is_valid(cls, value: str) -> str:
        return validate_username(value)

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("password")
    @classmethod
    def password_is_strong(cls, value: str) -> str:
        return validate_password(value)

    @model_validator(mode="after")
    def passwords_match(self) -> "RegisterRequest":
        # Compare without echoing either value in the validation error.
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def email_is_normalized(cls, value: str) -> str:
        return validate_email(value)


class UserProfile(BaseModel):
    id: int
    username: str
    email: str
    role: Literal["admin", "user"]
    is_active: bool
    created_at: str
    updated_at: str


class SessionInfo(BaseModel):
    user: UserProfile
    csrf_token: str
