from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.core.auth import current_subject
from app.core.jobs import submit
from app.crypto_boundary import client
from app.models.envelope import wrap, unwrap
from app.store import store

router = APIRouter()

# Seconds the client should wait before re-requesting a not-yet-ready vectorSet.
# Server-determined per the spec; 30 matches the spec's messaging example.
RETRY_SECONDS = 30


def _session_or_404(session_id: int):
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test session not found")
    return session


@router.get("/testSessions/{session_id}/vectorSets/{vs_id}")
def get_vector_set(session_id: int, vs_id: int, _: str = Depends(current_subject)) -> list:
    session = _session_or_404(session_id)
    vs = store.get_vector_set(session, vs_id)
    if vs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vector set not found")
    if vs.status == "expired":
        return wrap({"vsId": vs.vs_id, "status": "expired"})
    if vs.status == "generating" or vs.prompt is None:
        # Vectors not ready yet: tell the client to poll again (a separate
        # polling point from the results poll). See store.VectorSet lifecycle.
        return wrap({"vsId": vs.vs_id, "retry": RETRY_SECONDS})
    if vs.status == "ready":
        vs.status = "prompt_retrieved"
    # Stamp our resource id so it matches the URL (the stub fixture carries its
    # own vsId, which must not leak; the real module is given the vsId to echo).
    return wrap({**vs.prompt, "vsId": vs.vs_id})


@router.post("/testSessions/{session_id}/vectorSets/{vs_id}/results")
def submit_results(
    session_id: int, vs_id: int, body: list = Body(...), _: str = Depends(current_subject)
) -> list:
    session = _session_or_404(session_id)
    vs = store.get_vector_set(session, vs_id)
    if vs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vector set not found")
    response = unwrap(body)
    vs.response = response
    vs.status = "response_submitted"

    async def _run(rid: int) -> None:
        vs.validation = client.validate(vs.mode_folder, response)  # stub
        vs.status = "disposition"
        store.complete_request(
            rid, f"/acvp/v1/testSessions/{session_id}/vectorSets/{vs_id}/results"
        )

    rid = submit(_run)
    return wrap({"url": f"/acvp/v1/requests/{rid}"})


@router.get("/testSessions/{session_id}/vectorSets/{vs_id}/results")
def get_results(session_id: int, vs_id: int, _: str = Depends(current_subject)) -> list:
    session = _session_or_404(session_id)
    vs = store.get_vector_set(session, vs_id)
    if vs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vector set not found")
    # Spec: results may be requested at any time; the disposition reflects how
    # far processing has got. The payload is wrapped in a "results" object.
    base = vs.validation if vs.validation is not None else {}
    results = {
        "vsId": vs.vs_id,  # our resource id, not the stub fixture's baked-in vsId
        "disposition": vs.disposition(),
        "tests": base.get("tests", []),
    }
    return wrap({"results": results})
