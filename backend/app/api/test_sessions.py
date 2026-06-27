from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.core.auth import create_access_token, current_subject
from app.core.config import get_settings
from app.core.jobs import run_background
from app.crypto_boundary import client
from app.models.envelope import wrap, unwrap
from app.store import VectorSet, store

router = APIRouter()

# Map a registered algorithm/mode/revision to its NIST fixture folder (stub wiring).
_MODE_FOLDER = {
    ("ML-KEM", "keyGen", "FIPS203"): "ML-KEM-keyGen-FIPS203",
    ("ML-KEM", "encapDecap", "FIPS203"): "ML-KEM-encapDecap-FIPS203",
    ("ML-DSA", "keyGen", "FIPS204"): "ML-DSA-keyGen-FIPS204",
    ("ML-DSA", "sigGen", "FIPS204"): "ML-DSA-sigGen-FIPS204",
    ("ML-DSA", "sigVer", "FIPS204"): "ML-DSA-sigVer-FIPS204",
}


def _start_generation(vs: VectorSet) -> None:
    """Kick off vector generation in the background.

    The crypto module (stubbed by NIST fixtures) generates the prompt; until it
    lands the vectorSet GET returns a `retry` signal. See app/core/jobs.py.
    """

    async def _gen() -> None:
        vs.prompt = client.generate(vs.mode_folder)  # stub: NIST golden prompt
        vs.status = "ready"

    run_background(_gen)


def _iso(dt: datetime) -> str:
    """ISO-8601 UTC timestamp, e.g. 2018-05-31T12:03:43Z (spec format)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _session_passed(session) -> bool:
    """True only when every vectorSet has a passed disposition."""
    return bool(session.vector_sets) and all(
        vs.disposition() == "passed" for vs in session.vector_sets
    )


def _session_base(session) -> dict:
    """Fields common to the POST and GET test-session objects."""
    return {
        "url": f"/acvp/v1/testSessions/{session.session_id}",
        "acvpVersion": get_settings().acv_version,
        "createdOn": session.created_on,
        "expiresOn": session.expires_on,
        "encryptAtRest": session.encrypt_at_rest,
        "publishable": session.publishable,
        "passed": _session_passed(session),
        "isSample": session.is_sample,
    }


@router.post("/testSessions")
def create_test_session(body: list = Body(...), _: str = Depends(current_subject)) -> list:
    payload = unwrap(body)
    session = store.create_session()
    session.is_sample = bool(payload.get("isSample", False))
    session.encrypt_at_rest = bool(payload.get("encryptAtRest", False))
    now = datetime.now(timezone.utc)
    session.created_on = _iso(now)
    session.expires_on = _iso(now + timedelta(seconds=get_settings().session_expire_seconds))
    # Per-session JWT credential (HS256). [HUMAN REVIEW]
    session.access_token = create_access_token(f"session:{session.session_id}")

    for algo in payload.get("algorithms", []):
        key = (algo.get("algorithm"), algo.get("mode"), algo.get("revision"))
        folder = _MODE_FOLDER.get(key)
        if folder is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported algorithm: {key}")
        vs = store.add_vector_set(session, folder)
        _start_generation(vs)

    return wrap(
        {
            **_session_base(session),
            "vectorSetUrls": [
                f"/acvp/v1/testSessions/{session.session_id}/vectorSets/{v.vs_id}"
                for v in session.vector_sets
            ],
            "accessToken": session.access_token,
        }
    )


@router.get("/testSessions/{session_id}")
def get_test_session(session_id: int, _: str = Depends(current_subject)) -> list:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test session not found")
    return wrap(
        {
            **_session_base(session),
            "vectorSetsUrl": f"/acvp/v1/testSessions/{session_id}/vectorSets",
        }
    )


@router.get("/testSessions/{session_id}/results")
def get_session_results(session_id: int, _: str = Depends(current_subject)) -> list:
    """Session-level disposition summary across every vectorSet.

    `passed` is true only when every vectorSet has passed; per-vectorSet status
    uses the disposition vocabulary so the client can show more than pass/fail.
    """
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test session not found")

    results = [
        {
            "vectorSetUrl": f"/acvp/v1/testSessions/{session_id}/vectorSets/{vs.vs_id}",
            "status": vs.disposition(),
        }
        for vs in session.vector_sets
    ]
    passed = bool(session.vector_sets) and all(r["status"] == "passed" for r in results)
    return wrap({"passed": passed, "results": results})
