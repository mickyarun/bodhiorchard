# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pydantic schemas for authentication endpoints."""

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Schema for user login."""

    email: EmailStr
    password: str = Field(..., min_length=1)
    org_slug: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """Schema for user registration."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    org_slug: str = Field(..., min_length=1, max_length=100)
    org_name: str | None = None


class TokenResponse(BaseModel):
    """Schema for JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    """Schema for changing own password."""

    new_password: str = Field(..., min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    """Schema for token refresh."""

    refresh_token: str
