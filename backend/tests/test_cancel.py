"""Cancelling a test session (spec 12.16.5) and a vector set (spec 12.17.3).

Spec 12.16.5: "Marks a test session as being cancelled and may be deleted by the
server. Further operations with the test session resource may return 404 HTTP
Status."

Spec 12.17.3: "Cancel testing for a specific Vector Set."

The security-relevant part is the one the spec does NOT spell out: cancelling a
vector set must not become a way to make a failing session pass by deleting the
inconvenient vector sets. A session with cancelled testing can never be certified.

The other part the spec does not spell out is timing: generation and validation run
on background threads, so a cancel can land while one is in flight. The cancel must
win — see the two "not_undone" tests at the bottom and VectorSet.settle.
"""
import threading
import time

import pytest

from helpers import await_generation, golden_response, registration, session_headers

from app.core.config import get_settings
from app.crypto_boundary import client as boundary
from app.store import store

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _register(client, v, auth_header, modes=("ML-KEM-keyGen-FIPS203",)):
    reg = [{"acvVersion": v}, {"algorithms": [registration(m) for m in modes]}]
    body = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header).json()[1]
    return int(body["url"].rsplit("/", 1)[1]), body["vectorSetUrls"], session_headers(body)


def _drive_to_passed(client, v, sh, vs_url, mode="ML-KEM-keyGen-FIPS203"):
    vs_id = int(vs_url.rsplit("/", 1)[1])
    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=sh).json()[1]:
            break
        time.sleep(0.02)
    client.post(vs_url + "/results",
                json=[{"acvVersion": v}, golden_response(vs_id, mode)], headers=sh)
    for _ in range(50):
        if client.get(vs_url + "/results", headers=sh).json()[1]["results"]["disposition"] == "passed":
            break
        time.sleep(0.02)


# --- cancel a test session ------------------------------------------------------

def test_cancel_test_session(client, acv_version, auth_header):
    sid, vs_urls, sh = _register(client, acv_version, auth_header)

    assert client.delete(f"/acvp/v1/testSessions/{sid}", headers=sh).status_code == 200

    # Spec: further operations on a cancelled session may 404.
    assert client.get(f"/acvp/v1/testSessions/{sid}", headers=sh).status_code == 404
    assert client.get(f"/acvp/v1/testSessions/{sid}/results", headers=sh).status_code == 404
    assert client.get(f"/acvp/v1/testSessions/{sid}/vectorSets", headers=sh).status_code == 404
    assert client.get(vs_urls[0], headers=sh).status_code == 404


def test_cancel_test_session_is_idempotent_404(client, acv_version, auth_header):
    sid, _, sh = _register(client, acv_version, auth_header)
    assert client.delete(f"/acvp/v1/testSessions/{sid}", headers=sh).status_code == 200
    assert client.delete(f"/acvp/v1/testSessions/{sid}", headers=sh).status_code == 404


def test_cancel_test_session_requires_its_own_token(client, acv_version, auth_header):
    sid, _, _ = _register(client, acv_version, auth_header)
    # The login token is not the session's token: session-scoped authz still applies.
    assert client.delete(f"/acvp/v1/testSessions/{sid}", headers=auth_header).status_code == 403


# --- cancel a vector set --------------------------------------------------------

def test_cancel_vector_set(client, acv_version, auth_header):
    sid, vs_urls, sh = _register(client, acv_version, auth_header)
    vs_url = vs_urls[0]
    await_generation(sid, int(vs_url.rsplit("/", 1)[1]))

    assert client.delete(vs_url, headers=sh).status_code == 200

    # The cancelled vector set is gone: no prompt, no submission, no results.
    assert client.get(vs_url, headers=sh).status_code == 404
    assert client.get(vs_url + "/results", headers=sh).status_code == 404
    submission = [{"acvVersion": acv_version}, golden_response(int(vs_url.rsplit("/", 1)[1]))]
    assert client.post(vs_url + "/results", json=submission, headers=sh).status_code == 404

    # ...and it drops out of the session's vector set listing.
    listing = client.get(f"/acvp/v1/testSessions/{sid}/vectorSets", headers=sh).json()[1]
    assert listing["vectorSetUrls"] == []


def test_cancel_vector_set_is_idempotent_404(client, acv_version, auth_header):
    sid, vs_urls, sh = _register(client, acv_version, auth_header)
    await_generation(sid, int(vs_urls[0].rsplit("/", 1)[1]))
    assert client.delete(vs_urls[0], headers=sh).status_code == 200
    assert client.delete(vs_urls[0], headers=sh).status_code == 404


# --- cancel while a background task is in flight ---------------------------------
#
# Generation and validation run on threads (app.core.jobs). Before VectorSet.settle,
# both wrote `vs.status` unconditionally on completion — so a cancel that landed
# mid-flight was silently overwritten and the vector set came back from the dead.
# With the fixture provider the window is only microseconds wide; with the real NIST
# GenVal engine it is seconds. These tests hold the window open on purpose.

def _blocked(monkeypatch, name):
    """Stall crypto_boundary.<name> until the returned event is set."""
    real, release = getattr(boundary, name), threading.Event()

    def stalled(*args, **kwargs):
        release.wait(5)
        return real(*args, **kwargs)

    monkeypatch.setattr(boundary, name, stalled)
    return release


def _assert_stays_cancelled(client, sid, vs_url, sh, seconds=0.5):
    """The background thread has been released; give it every chance to misbehave."""
    vs = store.get_vector_set(store.get_session(sid), int(vs_url.rsplit("/", 1)[1]),
                              include_cancelled=True)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        assert vs.status == "cancelled", f"cancel was undone: status became {vs.status!r}"
        time.sleep(0.01)
    # And the cancel still holds at the API surface.
    assert client.get(vs_url, headers=sh).status_code == 404
    listing = client.get(f"/acvp/v1/testSessions/{sid}/vectorSets", headers=sh).json()[1]
    assert listing["vectorSetUrls"] == []


def test_cancel_during_generation_is_not_undone(client, acv_version, auth_header, monkeypatch):
    release = _blocked(monkeypatch, "generate")
    sid, vs_urls, sh = _register(client, acv_version, auth_header)

    # Generation is stalled, so the vector set is still "generating" — cancel it now.
    assert client.delete(vs_urls[0], headers=sh).status_code == 200

    release.set()  # the generate thread now completes and tries to write "ready"
    _assert_stays_cancelled(client, sid, vs_urls[0], sh)


def test_cancel_during_validation_is_not_undone(client, acv_version, auth_header, monkeypatch):
    sid, vs_urls, sh = _register(client, acv_version, auth_header)
    vs_url = vs_urls[0]
    vs_id = int(vs_url.rsplit("/", 1)[1])
    await_generation(sid, vs_id)
    client.get(vs_url, headers=sh)  # retrieve the prompt so results may be submitted

    release = _blocked(monkeypatch, "validate")
    submission = [{"acvVersion": acv_version}, golden_response(vs_id)]
    assert client.post(vs_url + "/results", json=submission, headers=sh).status_code == 200

    # Grading is stalled — cancel while the validate thread is in flight.
    assert client.delete(vs_url, headers=sh).status_code == 200

    release.set()  # the validate thread now completes and tries to write "disposition"
    _assert_stays_cancelled(client, sid, vs_url, sh)


def test_cancelling_a_vector_set_cannot_buy_a_pass(client, acv_version, auth_header):
    """Cancel the vector set you are failing -> the session still must not pass.

    Otherwise DELETE is a certification bypass: fail ML-DSA, delete it, and certify
    on the strength of the ML-KEM set alone.
    """
    v = acv_version
    sid, vs_urls, sh = _register(
        client, v, auth_header, modes=("ML-KEM-keyGen-FIPS203", "ML-DSA-keyGen-FIPS204")
    )
    kem_url, dsa_url = vs_urls
    _drive_to_passed(client, v, sh, kem_url, "ML-KEM-keyGen-FIPS203")
    await_generation(sid, int(dsa_url.rsplit("/", 1)[1]))

    # Only the ML-KEM set passed; the ML-DSA set was never answered.
    assert client.delete(dsa_url, headers=sh).status_code == 200

    info = client.get(f"/acvp/v1/testSessions/{sid}", headers=sh).json()[1]
    assert info["passed"] is False
    assert info["publishable"] is False

    results = client.get(f"/acvp/v1/testSessions/{sid}/results", headers=sh).json()[1]
    assert results["passed"] is False

    cert = [{"acvVersion": v}, {"moduleUrl": "/acvp/v1/modules/1", "oeUrl": "/acvp/v1/oes/1"}]
    assert client.put(f"/acvp/v1/testSessions/{sid}", json=cert, headers=sh).status_code == 403
