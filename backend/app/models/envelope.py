from typing import Any

from fastapi import HTTPException, status

from app.core.config import get_settings


def wrap(payload: dict[str, Any]) -> list[Any]:
    """Wrap a payload object in the ACVP version envelope."""
    return [{"acvVersion": get_settings().acv_version}, payload]


def unwrap(body: Any) -> dict[str, Any]:
    """Validate the ACVP envelope and return the inner payload.

    Wire format: [{"acvVersion": "1.0"}, { ...payload... }]
    """
    s = get_settings()
    if not isinstance(body, list) or len(body) != 2 or not isinstance(body[0], dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "malformed ACVP envelope")
    version = body[0].get("acvVersion")
    if version != s.acv_version:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"unsupported acvVersion: {version!r} (expected {s.acv_version!r})",
        )
    payload = body[1]
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "envelope payload must be an object")
    return payload
