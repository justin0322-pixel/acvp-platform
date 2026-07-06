"""Per-mode registration (capability) validation at POST /testSessions.

The NIST registration.json fixtures are the positive oracle: each must be
accepted verbatim. Malformed capabilities — bad parameterSets, missing required
fields, fields from another mode, unknown fields — must be rejected with 400,
and the accepted capabilities must be stored for the crypto boundary to use.
"""
import pytest

from app.core.config import get_settings
from app.store import store

from helpers import registration

_MODES = [
    "ML-KEM-keyGen-FIPS203",
    "ML-KEM-encapDecap-FIPS203",
    "ML-DSA-keyGen-FIPS204",
    "ML-DSA-sigGen-FIPS204",
    "ML-DSA-sigVer-FIPS204",
]

pytestmark = pytest.mark.skipif(
    not (get_settings().fixtures_dir / _MODES[0] / "registration.json").exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _post(client, v, auth_header, *algorithms):
    return client.post(
        "/acvp/v1/testSessions",
        json=[{"acvVersion": v}, {"algorithms": list(algorithms)}],
        headers=auth_header,
    )


# --- positive: every NIST example registration is accepted ------------------------

@pytest.mark.parametrize("mode_folder", _MODES)
def test_nist_registration_fixture_accepted(client, acv_version, auth_header, mode_folder):
    r = _post(client, acv_version, auth_header, registration(mode_folder))
    assert r.status_code == 200
    assert len(r.json()[1]["vectorSetUrls"]) == 1


def test_all_five_modes_in_one_session(client, acv_version, auth_header):
    r = _post(client, acv_version, auth_header, *(registration(m) for m in _MODES))
    assert r.status_code == 200
    assert len(r.json()[1]["vectorSetUrls"]) == 5


# --- negative: malformed capabilities are rejected with 400 ------------------------

def test_unknown_parameter_set_rejected(client, acv_version, auth_header):
    bad = {**registration("ML-KEM-keyGen-FIPS203"), "parameterSets": ["ML-KEM-9999"]}
    assert _post(client, acv_version, auth_header, bad).status_code == 400


def test_empty_parameter_sets_rejected(client, acv_version, auth_header):
    bad = {**registration("ML-KEM-keyGen-FIPS203"), "parameterSets": []}
    assert _post(client, acv_version, auth_header, bad).status_code == 400


def test_missing_parameter_sets_rejected(client, acv_version, auth_header):
    bad = registration("ML-KEM-keyGen-FIPS203")
    del bad["parameterSets"]
    assert _post(client, acv_version, auth_header, bad).status_code == 400


def test_encapdecap_missing_functions_rejected(client, acv_version, auth_header):
    bad = registration("ML-KEM-encapDecap-FIPS203")
    del bad["functions"]
    assert _post(client, acv_version, auth_header, bad).status_code == 400


def test_encapdecap_bad_function_rejected(client, acv_version, auth_header):
    bad = {**registration("ML-KEM-encapDecap-FIPS203"), "functions": ["sign"]}
    assert _post(client, acv_version, auth_header, bad).status_code == 400


def test_field_from_another_mode_rejected(client, acv_version, auth_header):
    # ML-KEM keyGen has no "functions" (that's encapDecap's field).
    bad = {**registration("ML-KEM-keyGen-FIPS203"), "functions": ["encapsulation"]}
    assert _post(client, acv_version, auth_header, bad).status_code == 400


def test_unknown_field_rejected(client, acv_version, auth_header):
    bad = {**registration("ML-DSA-keyGen-FIPS204"), "parameterSetz": ["ML-DSA-44"]}
    assert _post(client, acv_version, auth_header, bad).status_code == 400


def test_siggen_bad_hash_alg_rejected(client, acv_version, auth_header):
    bad = registration("ML-DSA-sigGen-FIPS204")
    bad["capabilities"][0]["hashAlgs"] = ["MD5"]
    assert _post(client, acv_version, auth_header, bad).status_code == 400


def test_sigver_kem_parameter_set_rejected(client, acv_version, auth_header):
    bad = registration("ML-DSA-sigVer-FIPS204")
    bad["capabilities"][0]["parameterSets"] = ["ML-KEM-512"]
    assert _post(client, acv_version, auth_header, bad).status_code == 400


def test_unsupported_algorithm_still_rejected(client, acv_version, auth_header):
    bad = {"algorithm": "AES", "mode": "GCM", "revision": "1.0"}
    assert _post(client, acv_version, auth_header, bad).status_code == 400


# --- accepted capabilities are stored for the crypto boundary ----------------------

def test_capabilities_stored_on_vector_set(client, acv_version, auth_header):
    reg = {**registration("ML-KEM-keyGen-FIPS203"), "parameterSets": ["ML-KEM-512"]}
    r = _post(client, acv_version, auth_header, reg)
    sid = int(r.json()[1]["url"].rsplit("/", 1)[1])
    vs = store.get_session(sid).vector_sets[0]
    assert vs.capabilities is not None
    assert vs.capabilities["parameterSets"] == ["ML-KEM-512"]
    assert vs.capabilities["algorithm"] == "ML-KEM"
