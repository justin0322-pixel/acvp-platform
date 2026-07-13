from datetime import timezone

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


def _expiry(vs) -> str | None:
    """The vector set's submission deadline, in the spec's format.

    Spec 14 pins this to "YYYY-MM-DD HH:MM:SS" (UTC) — deliberately NOT the
    ISO-8601 form the test session's createdOn/expiresOn use.
    """
    if vs.expires_at is None:
        return None
    return vs.expires_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


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
                for vs in session.active_vector_sets
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
    if vs.expired():
        # Spec 14: past the deadline the vectors are no longer served.
        return wrap({"vsId": vs.vs_id, "status": "expired"})
    if vs.status == "generating" or vs.prompt is None:
        # Vectors not ready yet: tell the client to poll again (a separate
        # polling point from the results poll). See store.VectorSet lifecycle.
        return wrap({"vsId": vs.vs_id, "retry": RETRY_SECONDS})
    if vs.status == "ready":
        vs.status = "prompt_retrieved"
    return wrap({**vs.prompt, "vsId": vs.vs_id, "expiry": _expiry(vs)})


@router.delete(
    "/testSessions/{testSessionId}/vectorSets/{vectorSetId}",
    status_code=status.HTTP_200_OK,
)
def cancel_vector_set(
    testSessionId: int, vectorSetId: int, _: int = Depends(require_session_access)
) -> Response:
    """Cancel testing of one vector set (spec 12.17.3).

    The set drops out of the session's listing and every operation on it 404s.
    Note it does NOT drop out of the session's verdict: see _session_passed —
    cancelling a vector set must not be a way to buy a pass.
    """
    session = _session_or_404(testSessionId)
    vs = store.get_vector_set(session, vectorSetId)
    if vs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vector set not found")
    # Takes the vector set's lock, so a generate/validate thread still in flight
    # cannot land its result afterwards and undo the cancel. See VectorSet.settle.
    vs.cancel()
    return Response(status_code=status.HTTP_200_OK)


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


def _cases_by_tc_id(payload: dict | None) -> dict[int, dict]:
    if not payload:
        return {}
    return {
        t["tcId"]: t
        for g in payload.get("testGroups", [])
        for t in g.get("tests", [])
        if isinstance(t.get("tcId"), int)
    }


def _disclose(tests: list[dict], vs) -> list[dict]:
    """Attach `expected`/`provided` to failing test cases when the client asked.

    Spec 12.17.4: with showExpected set on the submission, the server returns an
    `expected` and a `provided` object "for any failing test cases" — passing cases
    disclose nothing.

    [HUMAN REVIEW] This hands the answer key for failed cases back to the DUT. The
    spec sanctions it as a diagnostic aid, but it is a real disclosure channel: a
    client may submit deliberately wrong answers, read the expected values here,
    and resubmit them. Gate or disable it if that trade is not acceptable.
    """
    if not vs.show_expected:
        return tests
    expected, provided = _cases_by_tc_id(vs.expected), _cases_by_tc_id(vs.response)
    return [
        test if test.get("result") == "passed" else {
            **test,
            "expected": expected.get(test.get("tcId")),
            "provided": provided.get(test.get("tcId")),
        }
        for test in tests
    ]


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
    if vs.expired():
        # Spec: (re)submission MUST occur prior to expiry.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "vector set has expired")
    if vs.status in ("generating", "ready") or vs.prompt is None:
        # Illegal transition: answers cannot exist for a prompt never retrieved.
        raise HTTPException(status.HTTP_409_CONFLICT, "vector set prompt has not been retrieved")

    response = unwrap(body)
    # showExpected is a protocol flag, not a test-case answer (spec 12.17.5.1).
    # Strip it here so it never reaches the crypto boundary as a response field.
    vs.show_expected = response.pop("showExpected", False) is True
    vs.missing_tc_ids = _validate_submission(response, vs)
    vs.response = response
    vs.validation = None  # clear any prior disposition while we re-validate
    vs.status = "response_submitted"
    if resubmit:
        vs.resubmit_count += 1

    async def _run() -> None:
        try:
            validation = client.validate(
                vs.internal_projection, response, vs.mode_folder,
                session_id=session_id, vs_id=vs_id,
            )
            # settle(), not a bare assignment: the client may have cancelled this
            # vector set while we were grading it. See VectorSet.settle.
            vs.settle(validation=validation, status="disposition")
        except Exception as exc:  # engine/config/artifact failure -> disposition "error"
            vs.settle(error=str(exc), status="error")

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
        "tests": _disclose(base.get("tests", []), vs),
    }
    return wrap({"results": results})
