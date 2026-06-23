from pydantic import BaseModel


class LoginPayload(BaseModel):
    password: str | None = None
    accessToken: str | None = None  # present on renewal


class LoginResult(BaseModel):
    accessToken: str
    largeEndpointRequired: bool = False
    sizeConstraint: int = -1
