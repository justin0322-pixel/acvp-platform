"""Map our validated capabilities to a NIST single-algorithm registration.json.

The NIST GenValApp is field-sensitive about registration input, so we build the
envelope explicitly rather than dumping every model field. The output shape is the
NIST registration.json the engine's `-c` / `-g` steps expect (see the vendored
tests/fixtures/nist/<MODE>/registration.json, which this reproduces verbatim).

Mirrors the FIPS 204 team's map_mldsa_registration_to_nist conditional-field rules,
extended to ML-KEM. No crypto here — pure field selection. [HUMAN REVIEW]
"""
from __future__ import annotations

from typing import Any


class UnsupportedRegistration(ValueError):
    pass


def to_nist_registration(capability: dict[str, Any], *, vs_id: int, is_sample: bool) -> dict:
    """Build the NIST registration envelope for one algorithm/mode.

    `capability` is the validated capabilities object (our Pydantic model_dump,
    minus vsId/isSample). The engine gates a few ML-DSA fields on the signature
    interfaces, so we include them conditionally rather than unconditionally.
    """
    algorithm = capability.get("algorithm")
    mode = capability.get("mode")
    revision = capability.get("revision")

    reg: dict[str, Any] = {
        "vsId": vs_id,
        "algorithm": algorithm,
        "mode": mode,
        "revision": revision,
        "isSample": is_sample,
    }

    key = (algorithm, mode)
    if key in {("ML-KEM", "keyGen"), ("ML-DSA", "keyGen")}:
        reg["parameterSets"] = capability["parameterSets"]
    elif key == ("ML-KEM", "encapDecap"):
        reg["parameterSets"] = capability["parameterSets"]
        reg["functions"] = capability["functions"]
    elif key in {("ML-DSA", "sigGen"), ("ML-DSA", "sigVer")}:
        interfaces = capability["signatureInterfaces"]
        reg["capabilities"] = capability["capabilities"]
        reg["signatureInterfaces"] = interfaces
        if mode == "sigGen":
            reg["deterministic"] = capability["deterministic"]
        # externalMu applies to the internal interface; preHash to the external one.
        if "internal" in interfaces:
            reg["externalMu"] = capability["externalMu"]
        if "external" in interfaces:
            reg["preHash"] = capability["preHash"]
    else:
        raise UnsupportedRegistration(f"unsupported (algorithm, mode) for NIST registration: {key}")

    return reg
