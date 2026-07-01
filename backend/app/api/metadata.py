"""Metadata resource stubs (modules, operating environments).

Minimal placeholders so certification can reference moduleUrl/oeUrl. A full
implementation would add the create/get/update flows from the spec's metadata
sections; the prototype only needs the listings to exist.
"""
from fastapi import APIRouter, Depends

from app.core.auth import current_subject
from app.models.envelope import wrap

router = APIRouter()


def _paged(resource: str, data: list, *, limit: int = 20) -> dict:
    """An ACVP paged response (spec: totalCount/incomplete/links/data)."""
    page = f"/acvp/v1/{resource}?offset=0&limit={limit}"
    return {
        "totalCount": len(data),
        "incomplete": False,
        "links": {"first": page, "next": None, "prev": None, "last": page},
        "data": data,
    }


@router.get("/modules")
def list_modules(_: str = Depends(current_subject)) -> list:
    return wrap(_paged("modules", []))


@router.get("/oes")
def list_oes(_: str = Depends(current_subject)) -> list:
    return wrap(_paged("oes", []))
