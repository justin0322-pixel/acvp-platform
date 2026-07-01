from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from app.core.auth import current_subject
from app.core.jobs import run_background
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


@router.get("/testSessions/{session_id}/vectorSets")
def list_vector_sets(session_id: int, _: str = Depends(current_subject)) -> list:
    """List the session's vector sets. Spec: {"vectorSetUrls": [...]} only."""
    session = _session_or_404(session_id)
    return wrap(
        {
            "vectorSetUrls": [
                f"/acvp/v1/testSessions/{session_id}/vectorSets/{vs.vs_id}"
                for vs in session.vector_sets
            ]
        }
    )


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
    return wrap({**vs.prompt, "vsId": vs.vs_id})


@router.get("/testSessions/{session_id}/vectorSets/{vs_id}/expected")
def get_expected(session_id: int, vs_id: int, _: str = Depends(current_subject)) -> list:

    session = _session_or_404(session_id)
    vs = store.get_vector_set(session, vs_id)
    if vs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vector set not found")
    if not session.is_sample:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "expected results are only available for sample sessions"
        )
    expected = client.expected(vs.mode_folder)  # stub: NIST golden answer key
    # Stamp our resource id so the vsId matches the URL (see get_vector_set).
    return wrap({**expected, "vsId": vs.vs_id})


def _accept_results(session_id: int, vs_id: int, body: list, *, resubmit: bool) -> Response:

    session = _session_or_404(session_id)
    vs = store.get_vector_set(session, vs_id)
    if vs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vector set not found")
    if vs.status == "expired":
        # Spec: (re)submission MUST occur prior to expiry.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "vector set has expired")

    response = unwrap(body)
    vs.response = response
    vs.validation = None  # clear any prior disposition while we re-validate
    vs.status = "response_submitted"
    if resubmit:
        vs.resubmit_count += 1

    async def _run() -> None:
        vs.validation = client.validate(vs.mode_folder, response)  # stub
        vs.status = "disposition"

    run_background(_run)
    return Response(status_code=status.HTTP_200_OK)


@router.post(
    "/testSessions/{session_id}/vectorSets/{vs_id}/results",
    status_code=status.HTTP_200_OK,
)
def submit_results(
    session_id: int, vs_id: int, body: list = Body(...), _: str = Depends(current_subject)
) -> Response:
    """Initial submission of a vector set's responses."""
    return _accept_results(session_id, vs_id, body, resubmit=False)


@router.put(
    "/testSessions/{session_id}/vectorSets/{vs_id}/results",
    status_code=status.HTTP_200_OK,
)
def resubmit_results(
    session_id: int, vs_id: int, body: list = Body(...), _: str = Depends(current_subject)
) -> Response:
    """Resubmit an entire vector set after a failure (spec: identical to POST)."""
    return _accept_results(session_id, vs_id, body, resubmit=True)


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
