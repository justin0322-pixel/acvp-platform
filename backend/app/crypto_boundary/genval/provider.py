"""Abstract Gen/Val provider boundary (ported from the FIPS 204 team's genval).

Any crypto engine (NIST GenValApp today; an HTTP microservice later) implements
this interface. Keeping the boundary abstract is what lets the engine's language
and runtime stay opaque to the rest of the server.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict

from .artifacts import GenValArtifacts


class GenValProvider(ABC):
    @abstractmethod
    def check_registration(self, registration: Dict[str, Any], work_dir: Path) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def generate(self, registration: Dict[str, Any], work_dir: Path) -> GenValArtifacts:
        raise NotImplementedError

    @abstractmethod
    def validate(self, internal_projection: Path, response: Path, work_dir: Path) -> Path:
        raise NotImplementedError
