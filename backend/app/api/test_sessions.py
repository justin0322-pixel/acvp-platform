from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.core.auth import current_subject
from app.models.envelope import wrap, unwrap
from app.store import store

router = APIRouter()

# Map a registered algorithm/mode/revision to its NIST fixture folder (stub wiring).
_MODE_FOLDER = {
    ("ML-KEM", "keyGen", "FIPS203"): "ML-KEM-keyGen-FIPS203",
    ("ML-KEM", "encapDecap", "FIPS203"): "ML-KEM-encapDecap-FIPS203",
    ("ML-DSA", "keyGen", "FIPS204"): "ML-DSA-keyGen-FIPS204",
    ("ML-DSA", "sigGen", "FIPS204"): "ML-DSA-sigGen-FIPS204",
    ("ML-DSA", "sigVer", "FIPS204"): "ML-DSA-sigVer-FIPS204",
}


@router.post("/testSessions")
def create_test_session(body: list = Body(...), _: str = Depends(current_subject)) -> list:
    payload = unwrap(body)
    session = store.create_session()
    for algo in payload.get("algorithms", []):
        key = (algo.get("algorithm"), algo.get("mode"), algo.get("revision"))
        folder = _MODE_FOLDER.get(key)
        if folder is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported algorithm: {key}")
        store.add_vector_set(session, folder)
    return wrap(
        {
            "url": f"/acvp/v1/testSessions/{session.session_id}",
            "vectorSetUrls": [
                f"/acvp/v1/testSessions/{session.session_id}/vectorSets/{v.vs_id}"
                for v in session.vector_sets
            ],
        }
    )


@router.get("/testSessions/{session_id}")
def get_test_session(session_id: int, _: str = Depends(current_subject)) -> list:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test session not found")
    return wrap(
        {
            "url": f"/acvp/v1/testSessions/{session_id}",
            "vectorSetsUrl": f"/acvp/v1/testSessions/{session_id}/vectorSets",
            "passed": session.passed,
        }
    )


def _disposition(vs) -> str:
    """Map a vectorSet's lifecycle state to an ACVP disposition value.

    The seven disposition states are passed / failed / incomplete / unreceived /
    missing / expired / error. Here we cover the states reachable in the stub
    flow: an expired vectorSet, a validated one (use the crypto module's
    disposition verbatim), and one whose answers are not in yet (incomplete).
    """
    if vs.status == "expired":
        return "expired"
    if vs.validation is not None:
        return vs.validation.get("disposition", "error")
    return "incomplete"


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
            "status": _disposition(vs),
        }
        for vs in session.vector_sets
    ]
    passed = bool(session.vector_sets) and all(r["status"] == "passed" for r in results)
    return wrap({"passed": passed, "results": results})
