from pydantic import BaseModel


class LoginPayload(BaseModel):
    password: str | None = None
    accessToken: str | None = None  # present on renewal


class LoginResult(BaseModel):
    accessToken: str
    largeEndpointRequired: bool = False
    sizeConstraint: int = -1


class LoginRefreshPayload(BaseModel):
    password: str
    accessToken: list[str]  # one or more (session) tokens to refresh


class LoginRefreshResult(BaseModel):
    accessToken: list[str]  # refreshed tokens, in the same order
    largeEndpointRequired: bool = False
    sizeConstraint: int = -1
