"""Per-mode capability registration models (draft-celi-acvp-ml-kem / -ml-dsa).

The NIST registration.json fixtures are the schema of record: each model accepts
its fixture verbatim and rejects unknown fields, foreign-mode fields, and values
outside the spec's vocabularies. The validated capabilities are what the crypto
boundary's generate() will receive once the real 203/204 module lands.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MlKemParameterSet = Literal["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"]
MlDsaParameterSet = Literal["ML-DSA-44", "ML-DSA-65", "ML-DSA-87"]

HashAlg = Literal[
    "SHA2-224", "SHA2-256", "SHA2-384", "SHA2-512", "SHA2-512/224", "SHA2-512/256",
    "SHA3-224", "SHA3-256", "SHA3-384", "SHA3-512", "SHAKE-128", "SHAKE-256",
]


class _Registration(BaseModel):
    """Common shell. vsId/isSample appear in the NIST gen-val files; tolerate them."""
    model_config = ConfigDict(extra="forbid")

    vsId: int | None = None
    isSample: bool | None = None


class _Domain(BaseModel):
    """A spec numeric domain: {"min": N, "max": N, "increment": N}."""
    model_config = ConfigDict(extra="forbid")

    min: int
    max: int
    increment: int


class MlKemKeyGenRegistration(_Registration):
    algorithm: Literal["ML-KEM"]
    mode: Literal["keyGen"]
    revision: Literal["FIPS203"]
    parameterSets: list[MlKemParameterSet] = Field(min_length=1)


class MlKemEncapDecapRegistration(_Registration):
    algorithm: Literal["ML-KEM"]
    mode: Literal["encapDecap"]
    revision: Literal["FIPS203"]
    parameterSets: list[MlKemParameterSet] = Field(min_length=1)
    functions: list[
        Literal["encapsulation", "decapsulation", "encapsulationKeyCheck", "decapsulationKeyCheck"]
    ] = Field(min_length=1)


class MlDsaKeyGenRegistration(_Registration):
    algorithm: Literal["ML-DSA"]
    mode: Literal["keyGen"]
    revision: Literal["FIPS204"]
    parameterSets: list[MlDsaParameterSet] = Field(min_length=1)


class MlDsaSignatureCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameterSets: list[MlDsaParameterSet] = Field(min_length=1)
    messageLength: list[_Domain] = Field(min_length=1)
    hashAlgs: list[HashAlg] | None = None      # required only when preHash is tested
    contextLength: list[_Domain] | None = None  # applies to the external interface


class MlDsaSigGenRegistration(_Registration):
    algorithm: Literal["ML-DSA"]
    mode: Literal["sigGen"]
    revision: Literal["FIPS204"]
    capabilities: list[MlDsaSignatureCapability] = Field(min_length=1)
    deterministic: list[bool] = Field(min_length=1)
    externalMu: list[bool] = Field(min_length=1)
    signatureInterfaces: list[Literal["external", "internal"]] = Field(min_length=1)
    preHash: list[Literal["pure", "preHash"]] = Field(min_length=1)


class MlDsaSigVerRegistration(_Registration):
    algorithm: Literal["ML-DSA"]
    mode: Literal["sigVer"]
    revision: Literal["FIPS204"]
    capabilities: list[MlDsaSignatureCapability] = Field(min_length=1)
    externalMu: list[bool] = Field(min_length=1)
    signatureInterfaces: list[Literal["external", "internal"]] = Field(min_length=1)
    preHash: list[Literal["pure", "preHash"]] = Field(min_length=1)


REGISTRATION_MODELS: dict[tuple, type[_Registration]] = {
    ("ML-KEM", "keyGen", "FIPS203"): MlKemKeyGenRegistration,
    ("ML-KEM", "encapDecap", "FIPS203"): MlKemEncapDecapRegistration,
    ("ML-DSA", "keyGen", "FIPS204"): MlDsaKeyGenRegistration,
    ("ML-DSA", "sigGen", "FIPS204"): MlDsaSigGenRegistration,
    ("ML-DSA", "sigVer", "FIPS204"): MlDsaSigVerRegistration,
}


class UnsupportedAlgorithm(ValueError):
    pass


class InvalidRegistration(ValueError):
    pass


def parse_registration(algo: dict) -> _Registration:
    """Validate one algorithm capability object against its per-mode model."""
    key = (algo.get("algorithm"), algo.get("mode"), algo.get("revision"))
    model = REGISTRATION_MODELS.get(key)
    if model is None:
        raise UnsupportedAlgorithm(f"unsupported algorithm: {key}")
    try:
        return model.model_validate(algo)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "registration"
        raise InvalidRegistration(f"invalid registration for {key}: {where}: {first['msg']}")
