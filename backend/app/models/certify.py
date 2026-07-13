"""The Submit-For-Validation request body (spec 12.16.4.1).

Certification binds a passed test session to the module and operating environment
it was run against. Those references are what a certificate means, so they are
validated here rather than accepted on trust. [HUMAN REVIEW]
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class Prerequisite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: str
    validationId: str


class AlgorithmPrerequisites(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: str
    mode: str | None = None      # not all algorithms have a mode
    prerequisites: list[Prerequisite]


class CertifyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Spec: `module` MAY be used *instead of* moduleUrl (to create a new module
    # resource); likewise `oe` instead of oeUrl. Exactly one of each, never both.
    moduleUrl: str | None = None
    module: dict[str, Any] | None = None
    oeUrl: str | None = None
    oe: dict[str, Any] | None = None
    algorithmPrerequisites: list[AlgorithmPrerequisites] = []

    @model_validator(mode="after")
    def _one_reference_each(self) -> "CertifyPayload":
        if (self.moduleUrl is None) == (self.module is None):
            raise ValueError("exactly one of moduleUrl or module is required")
        if (self.oeUrl is None) == (self.oe is None):
            raise ValueError("exactly one of oeUrl or oe is required")
        return self
