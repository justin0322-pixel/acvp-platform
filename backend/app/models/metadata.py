"""Metadata resources: vendors, persons, modules, OEs, dependencies (spec 12.8-12.13).

These are what a certificate is *about* — the module, and the operating environment
it ran in. Certification binds a passed test session to them, so their references
have to resolve; see api/metadata.py for the reference checking.

Spec, on every create: "Any additional properties included in the request are
ignored." So these models deliberately do NOT forbid extras — unlike the algorithm
registrations, where an unknown field means the client got the contract wrong.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

# Spec 12.11 lists these lowercase, but its own example writes "Software".
# Accept either and normalise (see api/metadata.py).
ModuleType = Literal["software", "hardware", "firmware", "softwarehybrid", "firmwarehybrid"]


class PhoneNumber(BaseModel):
    number: str
    type: Literal["fax", "voice"]


class Address(BaseModel):
    street1: str | None = None
    street2: str | None = None
    street3: str | None = None
    locality: str | None = None
    region: str | None = None
    country: str | None = None
    postalCode: str | None = None


class VendorCreate(BaseModel):
    name: str
    website: str | None = None
    emails: list[str] = []
    phoneNumbers: list[PhoneNumber] = []
    addresses: list[Address] = []


class PersonCreate(BaseModel):
    fullName: str
    vendorUrl: str | None = None
    emails: list[str] = []
    phoneNumbers: list[PhoneNumber] = []


class ModuleCreate(BaseModel):
    # Spec 12.11.2.1: "name, vendorUrl, and description are required."
    name: str
    vendorUrl: str
    description: str
    version: str | None = None
    type: ModuleType | None = None
    website: str | None = None
    addressUrl: str | None = None
    contactUrls: list[str] = []

    @field_validator("type", mode="before")
    @classmethod
    def _normalise_type(cls, v: Any) -> Any:
        # The spec enumerates lowercase but its own example sends "Software".
        return v.lower() if isinstance(v, str) else v


class OeCreate(BaseModel):
    # Spec 12.12.2.1: "name is required. Other defined resource properties are OPTIONAL."
    name: str
    dependencyUrls: list[str] = []


class DependencyCreate(BaseModel):
    # Spec 12.13: the properties for a dependency vary by `type` — "a server MAY
    # choose to restrict or not restrict the range of name/value pairs available".
    # We do not restrict, so extras are kept rather than dropped.
    model_config = ConfigDict(extra="allow")

    type: str | None = None
    name: str | None = None
    description: str | None = None


# resource -> (model, [(field, resource it must point at)])
# The second element is what stops a certificate resting on a dangling reference.
METADATA_MODELS: dict[str, tuple[type[BaseModel], list[tuple[str, str]]]] = {
    "vendors": (VendorCreate, []),
    "persons": (PersonCreate, [("vendorUrl", "vendors")]),
    "modules": (ModuleCreate, [("vendorUrl", "vendors"), ("contactUrls", "persons")]),
    "oes": (OeCreate, [("dependencyUrls", "dependencies")]),
    "dependencies": (DependencyCreate, []),
}


def dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(exclude_none=True)
