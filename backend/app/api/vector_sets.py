from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from app.core.auth import require_session_access
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


@router.get("/testSessions/{testSessionId}/vectorSets")
def list_vector_sets(testSessionId: int, _: int = Depends(require_session_access)) -> list:
    """List the session's vector sets. Spec: {"vectorSetUrls": [...]} only."""
    session_id = testSessionId
    session = _session_or_404(session_id)
    return wrap(
        {
            "vectorSetUrls": [
                f"/acvp/v1/testSessions/{session_id}/vectorSets/{vs.vs_id}"
                for vs in session.vector_sets
            ]
        }
    )


@router.get("/testSessions/{testSessionId}/vectorSets/{vectorSetId}")
def get_vector_set(testSessionId: int, vectorSetId: int, _: int = Depends(require_session_access)) -> list:
    session_id, vs_id = testSessionId, vectorSetId
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


@router.get("/testSessions/{testSessionId}/vectorSets/{vectorSetId}/expected")
def get_expected(testSessionId: int, vectorSetId: int, _: int = Depends(require_session_access)) -> list:
    session_id, vs_id = testSessionId, vectorSetId
    session = _session_or_404(session_id)
    vs = store.get_vector_set(session, vs_id)
    if vs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vector set not found")
    if not session.is_sample:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "expected results are only available for sample sessions"
        )
    # Prefer the answer key persisted at generation; fall back to the fixture.
    expected = vs.expected if vs.expected is not None else client.expected_results(vs.mode_folder)
    # Stamp our resource id so the vsId matches the URL (see get_vector_set).
    return wrap({**expected, "vsId": vs.vs_id})


def _tc_ids(payload: dict) -> set[int]:
    return {t["tcId"] for g in payload.get("testGroups", []) for t in g.get("tests", [])}


def _validate_submission(response: dict, vs) -> list[int]:
    """Structural (non-crypto) checks on a submitted response.

    Returns the tcIds present in the prompt but absent from the submission —
    those grade the vector set `missing`. Unknown tcIds are a client error.
    """
    if response.get("vsId") != vs.vs_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "response vsId does not match the vector set")
    groups = response.get("testGroups")
    if not isinstance(groups, list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "response must contain a testGroups array")
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("tgId"), int) \
                or not isinstance(group.get("tests"), list) \
                or not all(isinstance(t, dict) and isinstance(t.get("tcId"), int) for t in group["tests"]):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "each testGroup must carry an integer tgId and a tests array of objects with integer tcIds",
            )

    prompt_ids, submitted_ids = _tc_ids(vs.prompt), _tc_ids(response)
    unknown = submitted_ids - prompt_ids
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"response contains tcIds not in the prompt: {sorted(unknown)[:5]}"
        )
    return sorted(prompt_ids - submitted_ids)


def _accept_results(session_id: int, vs_id: int, body: list, *, resubmit: bool) -> Response:

    session = _session_or_404(session_id)
    vs = store.get_vector_set(session, vs_id)
    if vs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vector set not found")
    if vs.status == "expired":
        # Spec: (re)submission MUST occur prior to expiry.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "vector set has expired")
    if vs.status in ("generating", "ready") or vs.prompt is None:
        # Illegal transition: answers cannot exist for a prompt never retrieved.
        raise HTTPException(status.HTTP_409_CONFLICT, "vector set prompt has not been retrieved")

    response = unwrap(body)
    vs.missing_tc_ids = _validate_submission(response, vs)
    vs.response = response
    vs.validation = None  # clear any prior disposition while we re-validate
    vs.status = "response_submitted"
    if resubmit:
        vs.resubmit_count += 1

    async def _run() -> None:
        try:
            vs.validation = client.validate(
                vs.internal_projection, response, vs.mode_folder,
                session_id=session_id, vs_id=vs_id,
            )
            vs.status = "disposition"
        except Exception as exc:  # engine/config/artifact failure -> disposition "error"
            vs.error = str(exc)
            vs.status = "error"

    run_background(_run)
    return Response(status_code=status.HTTP_200_OK)


@router.post(
    "/testSessions/{testSessionId}/vectorSets/{vectorSetId}/results",
    status_code=status.HTTP_200_OK,
)
def submit_results(
    testSessionId: int, vectorSetId: int, body: list = Body(...),
    _: int = Depends(require_session_access),
) -> Response:
    """Initial submission of a vector set's responses."""
    return _accept_results(testSessionId, vectorSetId, body, resubmit=False)


@router.put(
    "/testSessions/{testSessionId}/vectorSets/{vectorSetId}/results",
    status_code=status.HTTP_200_OK,
)
def resubmit_results(
    testSessionId: int, vectorSetId: int, body: list = Body(...),
    _: int = Depends(require_session_access),
) -> Response:
    """Resubmit an entire vector set after a failure (spec: identical to POST)."""
    return _accept_results(testSessionId, vectorSetId, body, resubmit=True)


@router.get("/testSessions/{testSessionId}/vectorSets/{vectorSetId}/results")
def get_results(testSessionId: int, vectorSetId: int, _: int = Depends(require_session_access)) -> list:
    session_id, vs_id = testSessionId, vectorSetId
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
