import time

import pytest

from helpers import registration, session_headers

from app.core.config import get_settings
from app.store import store

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _register(client, v, auth_header):
    reg = [{"acvVersion": v}, {"algorithms": [
        registration("ML-KEM-keyGen-FIPS203")
    ]}]
    r = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header)
    assert r.status_code == 200
    return r.json()[1]


def _ids(body):
    session_id = int(body["url"].rsplit("/", 1)[1])
    vs_url = body["vectorSetUrls"][0]
    vs_id = int(vs_url.rsplit("/", 1)[1])
    return session_id, vs_url, vs_id


def test_vectorset_retry_while_generating(client, acv_version, auth_header):
    body = _register(client, acv_version, auth_header)
    sh = session_headers(body)
    session_id, vs_url, vs_id = _ids(body)

    # Force the "still generating" state deterministically (no wall-clock races).
    vs = store.get_vector_set(store.get_session(session_id), vs_id)
    vs.status = "generating"
    vs.prompt = None

    r = client.get(vs_url, headers=sh)
    assert r.status_code == 200
    payload = r.json()[1]

    # Spec: retrieval before vectors are ready returns {vsId, retry} only.
    assert set(payload.keys()) == {"vsId", "retry"}
    assert payload["vsId"] == vs_id
    assert isinstance(payload["retry"], int) and payload["retry"] > 0
    assert "algorithm" not in payload  # no prompt leaked while generating


def test_vectorset_ready_returns_prompt(client, acv_version, auth_header):
    body = _register(client, acv_version, auth_header)
    sh = session_headers(body)
    _, vs_url, _ = _ids(body)

    payload = None
    for _ in range(50):
        payload = client.get(vs_url, headers=sh).json()[1]
        if "retry" not in payload:
            break
        time.sleep(0.02)

    assert payload is not None and "retry" not in payload
    assert payload["algorithm"] == "ML-KEM"
