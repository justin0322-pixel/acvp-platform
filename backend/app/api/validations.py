"""Validation (certificate) resources — produced by certifying a test session.

Certification returns a request whose approvedUrl points at /validations/{id};
this endpoint serves that resource so the reference resolves.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import current_subject
from app.models.envelope import wrap
from app.store import store

router = APIRouter()


@router.get("/validations/{validationId}")
def get_validation(validationId: int, _: str = Depends(current_subject)) -> list:
    v = store.get_validation(validationId)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "validation not found")
    return wrap(
        {
            "url": f"/acvp/v1/validations/{validationId}",
            "createdOn": v["created_on"],
            "testSessionUrl": f"/acvp/v1/testSessions/{v['session_id']}",
        }
    )
