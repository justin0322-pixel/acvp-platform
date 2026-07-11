"""to_nist_registration reproduces the NIST registration envelope for all 5 modes.

The vendored NIST registration.json fixtures are the schema of record: feeding the
mapper a fixture's capabilities (minus vsId/isSample) must reproduce that fixture
verbatim. Also checks the ML-DSA conditional-field gating the engine expects.
"""
import json

import pytest

from app.core.config import get_settings
from app.crypto_boundary.registration import UnsupportedRegistration, to_nist_registration

_MODES = [
    "ML-KEM-keyGen-FIPS203",
    "ML-KEM-encapDecap-FIPS203",
    "ML-DSA-keyGen-FIPS204",
    "ML-DSA-sigGen-FIPS204",
    "ML-DSA-sigVer-FIPS204",
]

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "registration.json"
pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _fixture_registration(mode_folder: str) -> dict:
    path = get_settings().fixtures_dir / mode_folder / "registration.json"
    return json.loads(path.read_text())


@pytest.mark.parametrize("mode_folder", _MODES)
def test_mapper_reproduces_nist_registration(mode_folder):
    fixture = _fixture_registration(mode_folder)
    capability = {k: v for k, v in fixture.items() if k not in ("vsId", "isSample")}
    mapped = to_nist_registration(
        capability, vs_id=fixture["vsId"], is_sample=fixture["isSample"]
    )
    assert mapped == fixture  # exact round-trip (dict equality ignores key order)


def test_siggen_gates_externalmu_to_internal_interface():
    fixture = _fixture_registration("ML-DSA-sigGen-FIPS204")
    capability = {k: v for k, v in fixture.items() if k not in ("vsId", "isSample")}
    capability["signatureInterfaces"] = ["external"]  # no internal -> drop externalMu
    mapped = to_nist_registration(capability, vs_id=1, is_sample=False)
    assert "externalMu" not in mapped
    assert "preHash" in mapped  # external present -> keep preHash


def test_sigver_gates_prehash_to_external_interface():
    fixture = _fixture_registration("ML-DSA-sigVer-FIPS204")
    capability = {k: v for k, v in fixture.items() if k not in ("vsId", "isSample")}
    capability["signatureInterfaces"] = ["internal"]  # no external -> drop preHash
    mapped = to_nist_registration(capability, vs_id=1, is_sample=False)
    assert "preHash" not in mapped
    assert "externalMu" in mapped  # internal present -> keep externalMu


def test_unsupported_mode_raises():
    with pytest.raises(UnsupportedRegistration):
        to_nist_registration(
            {"algorithm": "RSA", "mode": "keyGen", "revision": "FIPS186"},
            vs_id=1, is_sample=False,
        )
