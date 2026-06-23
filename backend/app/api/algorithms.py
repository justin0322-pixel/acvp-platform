from fastapi import APIRouter, Depends

from app.core.auth import current_subject
from app.models.envelope import wrap

router = APIRouter()

SUPPORTED = [
    {"algorithm": "ML-KEM", "mode": "keyGen", "revision": "FIPS203"},
    {"algorithm": "ML-KEM", "mode": "encapDecap", "revision": "FIPS203"},
    {"algorithm": "ML-DSA", "mode": "keyGen", "revision": "FIPS204"},
    {"algorithm": "ML-DSA", "mode": "sigGen", "revision": "FIPS204"},
    {"algorithm": "ML-DSA", "mode": "sigVer", "revision": "FIPS204"},
]


@router.get("/algorithms")
def list_algorithms(_: str = Depends(current_subject)) -> list:
    return wrap({"algorithms": SUPPORTED})
