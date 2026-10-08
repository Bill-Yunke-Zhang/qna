from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = None
    password: str | None = None
    netid: str | None = None  # dev-only fallback

    @model_validator(mode="after")
    def check_credentials(self) -> LoginRequest:
        has_password_creds = self.username and self.password
        has_netid = self.netid
        if not has_password_creds and not has_netid:
            raise ValueError("Provide username+password or netid (dev only)")
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TempTokenResponse(BaseModel):
    temp_token: str
    token_type: str = "bearer"


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
