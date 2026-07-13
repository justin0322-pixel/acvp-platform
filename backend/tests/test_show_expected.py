"""showExpected on results submission (spec 12.17.5.1 / 12.17.4).

Spec 12.17.5.1: "The showExpected property is optional; when included (and set to
true) the ACVP server will include additional information within the validation
response file described in Section 12.17.4."

Spec 12.17.4: "...additional information is provided back to the client for any
failing test cases. The additional information includes an 'expected' as well as
'provided' object..."

Grading is the crypto module's job, and the fixture stub returns the golden
validation verbatim rather than marking anything wrong. So — as elsewhere in this
suite — the crypto verdict is injected onto the vector set, and what is under test
is our disclosure logic: that `expected`/`provided` reach failing cases only.
"""
import time

import pytest

from helpers import await_validation, golden_response, registration, session_headers

from app.core.config import get_settings
from app.store import store

_MODE = "ML-KEM-keyGen-FIPS203"
_FIXTURE = get_settings().fixtures_dir / _MODE / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _submit(client, v, auth_header, *, show_expected: bool):
    """Register, retrieve the prompt, and submit the golden answers."""
    reg = [{"acvVersion": v}, {"algorithms": [registration(_MODE)]}]
    body = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header).json()[1]
    sh = session_headers(body)
    vs_url = body["vectorSetUrls"][0]
    sid, vs_id = int(body["url"].rsplit("/", 1)[1]), int(vs_url.rsplit("/", 1)[1])

    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=sh).json()[1]:
            break
        time.sleep(0.02)

    response = golden_response(vs_id, _MODE)
    if show_expected:
        response["showExpected"] = True
    assert client.post(
        vs_url + "/results", json=[{"acvVersion": v}, response], headers=sh
    ).status_code == 200
    return sid, vs_id, vs_url, sh


def _inject_verdict(sid: int, vs_id: int) -> tuple[int, int]:
    """Have the crypto module report one failing and one passing test case."""
    vs = await_validation(sid, vs_id)
    tc_ids = [t["tcId"] for g in vs.prompt["testGroups"] for t in g["tests"]]
    bad, good = tc_ids[0], tc_ids[1]
    vs.validation = {
        "vsId": vs_id,
        "disposition": "failed",
        "tests": [
            {"tcId": bad, "result": "failed", "reason": "wrong ek"},
            {"tcId": good, "result": "passed", "reason": ""},
        ],
    }
    return bad, good


def test_show_expected_discloses_only_failing_cases(client, acv_version, auth_header):
    sid, vs_id, vs_url, sh = _submit(client, acv_version, auth_header, show_expected=True)
    bad, good = _inject_verdict(sid, vs_id)

    tests = client.get(vs_url + "/results", headers=sh).json()[1]["results"]["tests"]
    by_tc = {t["tcId"]: t for t in tests}

    failing = by_tc[bad]
    assert failing["result"] == "failed"
    assert failing["expected"] is not None and failing["provided"] is not None
    # The disclosed objects are the answer key and what the client actually sent.
    assert failing["expected"]["tcId"] == bad
    assert failing["provided"]["tcId"] == bad

    passing = by_tc[good]
    assert "expected" not in passing and "provided" not in passing


def test_without_show_expected_nothing_is_disclosed(client, acv_version, auth_header):
    sid, vs_id, vs_url, sh = _submit(client, acv_version, auth_header, show_expected=False)
    bad, good = _inject_verdict(sid, vs_id)

    tests = client.get(vs_url + "/results", headers=sh).json()[1]["results"]["tests"]
    for test in tests:
        assert "expected" not in test and "provided" not in test


def test_show_expected_is_stripped_before_the_crypto_boundary(client, acv_version, auth_header):
    """showExpected is a protocol flag; the crypto module must never see it."""
    sid, vs_id, _, _ = _submit(client, acv_version, auth_header, show_expected=True)
    vs = store.get_vector_set(store.get_session(sid), vs_id)

    assert vs.show_expected is True
    assert "showExpected" not in vs.response
