"""Algorithm resources (spec 12.14). "The Algorithm resources are informational only."

The listing objects carry `id` / `name` / `mode` / `revision` per spec 12.14.1 —
note `name`, not `algorithm`. `algorithm` is the key used in a *registration*
(what the client asks to be tested on); this is the server's catalogue of what it
can test, which is a different thing.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import current_subject
from app.models.envelope import wrap

router = APIRouter()

SUPPORTED = [
    {"id": 1, "name": "ML-KEM", "mode": "keyGen", "revision": "FIPS203"},
    {"id": 2, "name": "ML-KEM", "mode": "encapDecap", "revision": "FIPS203"},
    {"id": 3, "name": "ML-DSA", "mode": "keyGen", "revision": "FIPS204"},
    {"id": 4, "name": "ML-DSA", "mode": "sigGen", "revision": "FIPS204"},
    {"id": 5, "name": "ML-DSA", "mode": "sigVer", "revision": "FIPS204"},
]


@router.get("/algorithms")
def list_algorithms(_: str = Depends(current_subject)) -> list:
    return wrap({"algorithms": SUPPORTED})


@router.get("/algorithms/{algorithmId}")
def get_algorithm(algorithmId: int, _: str = Depends(current_subject)) -> list:
    """Spec 12.14.2 (OPTIONAL): information about one algorithm."""
    algorithm = next((a for a in SUPPORTED if a["id"] == algorithmId), None)
    if algorithm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "algorithm not found")
    return wrap(algorithm)
