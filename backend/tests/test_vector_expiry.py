"""Vector set expiry (spec section 14, "Vector Set Expiration").

The spec requires three things of an expiring vector set:

  1. The delivered vector set carries an `expiry` value — a UTC timestamp string
     of the form "YYYY-MM-DD HH:MM:SS" (note: NOT the ISO-8601 form used by the
     test session's createdOn/expiresOn).
  2. Retrieving an expired vector set returns {"vsId": N, "status": "expired"}.
  3. Responses MUST be (re)submitted prior to expiry — a submission afterwards
     is refused.

Expiry is driven by the clock, so these tests set the deadline explicitly rather
than sleeping.
"""
import re
import time
from datetime import datetime, timedelta, timezone

import pytest

from helpers import golden_response, registration, session_headers

from app.core.config import get_settings
from app.store import store

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)

# Spec section 14: "a string value of the UTC timestamp using form
# 'YYYY-MM-DD HH:MM:SS'".
EXPIRY_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def _register(client, v, auth_header):
    reg = [{"acvVersion": v}, {"algorithms": [registration("ML-KEM-keyGen-FIPS203")]}]
    r = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header)
    assert r.status_code == 200
    return r.json()[1]


def _ids(body):
    session_id = int(body["url"].rsplit("/", 1)[1])
    vs_url = body["vectorSetUrls"][0]
    return session_id, vs_url, int(vs_url.rsplit("/", 1)[1])


def _await_prompt(client, vs_url, headers) -> dict:
    """Poll until generation finishes (the retry loop), then return the prompt."""
    for _ in range(50):
        payload = client.get(vs_url, headers=headers).json()[1]
        if "retry" not in payload:
            return payload
        time.sleep(0.02)
    raise AssertionError("vector set never became ready")


def _expire(session_id: int, vs_id: int) -> None:
    """Move the vector set's deadline into the past."""
    vs = store.get_vector_set(store.get_session(session_id), vs_id)
    vs.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)


def test_prompt_carries_expiry(client, acv_version, auth_header):
    body = _register(client, acv_version, auth_header)
    sh = session_headers(body)
    _, vs_url, _ = _ids(body)

    prompt = _await_prompt(client, vs_url, sh)

    assert "expiry" in prompt, "spec section 14: the vector set MUST carry an expiry value"
    assert EXPIRY_FORMAT.match(prompt["expiry"]), prompt["expiry"]
    # The deadline is in the future for a freshly generated vector set.
    deadline = datetime.strptime(prompt["expiry"], "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    assert deadline > datetime.now(timezone.utc)


def test_expired_vectorset_reports_expired_on_retrieval(client, acv_version, auth_header):
    body = _register(client, acv_version, auth_header)
    sh = session_headers(body)
    session_id, vs_url, vs_id = _ids(body)
    _await_prompt(client, vs_url, sh)

    _expire(session_id, vs_id)

    r = client.get(vs_url, headers=sh)
    assert r.status_code == 200
    payload = r.json()[1]
    # Spec section 14: the reply is exactly {vsId, status} — no prompt is served.
    assert payload == {"vsId": vs_id, "status": "expired"}


def test_expired_vectorset_refuses_submission(client, acv_version, auth_header):
    body = _register(client, acv_version, auth_header)
    sh = session_headers(body)
    session_id, vs_url, vs_id = _ids(body)
    _await_prompt(client, vs_url, sh)

    _expire(session_id, vs_id)

    submission = [{"acvVersion": acv_version}, golden_response(vs_id)]
    # Spec: "The resending of vector set responses MUST occur prior to expiry."
    assert client.post(f"{vs_url}/results", json=submission, headers=sh).status_code == 403
    assert client.put(f"{vs_url}/results", json=submission, headers=sh).status_code == 403


def test_expired_vectorset_disposition(client, acv_version, auth_header):
    body = _register(client, acv_version, auth_header)
    sh = session_headers(body)
    session_id, vs_url, vs_id = _ids(body)
    _await_prompt(client, vs_url, sh)

    _expire(session_id, vs_id)

    results = client.get(f"{vs_url}/results", headers=sh).json()[1]["results"]
    assert results["disposition"] == "expired"

    session_results = client.get(
        f"/acvp/v1/testSessions/{session_id}/results", headers=sh
    ).json()[1]
    assert session_results["passed"] is False
    assert session_results["results"][0]["status"] == "expired"


def test_passed_vectorset_expiring_afterwards_stays_passed(client, acv_version, auth_header):
    """Expiry is about the submission deadline, not about erasing a graded result."""
    body = _register(client, acv_version, auth_header)
    sh = session_headers(body)
    session_id, vs_url, vs_id = _ids(body)
    _await_prompt(client, vs_url, sh)

    submission = [{"acvVersion": acv_version}, golden_response(vs_id)]
    assert client.post(f"{vs_url}/results", json=submission, headers=sh).status_code == 200

    for _ in range(50):
        results = client.get(f"{vs_url}/results", headers=sh).json()[1]["results"]
        if results["disposition"] not in ("incomplete", "unreceived"):
            break
        time.sleep(0.02)
    assert results["disposition"] == "passed"

    _expire(session_id, vs_id)

    results = client.get(f"{vs_url}/results", headers=sh).json()[1]["results"]
    assert results["disposition"] == "passed"
