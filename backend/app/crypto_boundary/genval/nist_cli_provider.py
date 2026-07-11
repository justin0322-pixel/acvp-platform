"""Calls the NIST ACVP-Server GenValApp .NET runner across a process boundary.

Ported (near-verbatim) from the FIPS 204 team's `genval/nist_cli_provider.py`.
The runner is invoked as:
  - check:    dotnet GenValApp.dll -c registration.json
  - generate: dotnet GenValApp.dll -g registration.json
  - validate: dotnet GenValApp.dll -n internalProjection.json -b response.json
It requires an Orleans.ServerHost running separately (see scripts/nist/). The
runner is file/dir based: it reads/writes JSON files in `work_dir`.

[HUMAN REVIEW] crypto-boundary code — do not auto-merge.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .artifacts import GenValArtifacts
from .errors import GenValArtifactError, GenValConfigurationError, GenValExecutionError
from .provider import GenValProvider
from .settings import GenValSettings, get_genval_settings


class NistCliGenValProvider(GenValProvider):
    def __init__(self, settings: GenValSettings | None = None):
        self.settings = settings or get_genval_settings()

    def check_registration(self, registration: Dict[str, Any], work_dir: Path) -> Dict[str, Any]:
        work_dir.mkdir(parents=True, exist_ok=True)
        registration_path = work_dir / "registration.json"
        _write_json(registration_path, registration)
        completed = self._run(["-c", str(registration_path)], work_dir, "check")
        return {
            "status": "passed",
            "returnCode": completed.returncode,
            "stdout": str(work_dir / "check.stdout.txt"),
            "stderr": str(work_dir / "check.stderr.txt"),
        }

    def generate(self, registration: Dict[str, Any], work_dir: Path) -> GenValArtifacts:
        work_dir.mkdir(parents=True, exist_ok=True)
        registration_path = work_dir / "registration.json"
        _write_json(registration_path, registration)
        self._run(["-g", str(registration_path)], work_dir, "generation")

        prompt = _require_file(work_dir / "prompt.json")
        internal_projection = _require_file(work_dir / "internalProjection.json")
        expected_results = work_dir / "expectedResults.json"
        if not expected_results.exists():
            expected_results = None

        return GenValArtifacts(
            registration=registration_path,
            prompt=prompt,
            internal_projection=internal_projection,
            expected_results=expected_results,
            stdout=work_dir / "generation.stdout.txt",
            stderr=work_dir / "generation.stderr.txt",
        )

    def validate(self, internal_projection: Path, response: Path, work_dir: Path) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        internal_projection = _require_file(internal_projection)
        response = _require_file(response)
        validation_path = work_dir / "validation.json"
        if validation_path.exists():
            validation_path.unlink()
        self._run(
            ["-n", str(internal_projection), "-b", str(response)],
            work_dir,
            "validation",
        )
        return _require_file(validation_path)

    def _run(self, args: List[str], work_dir: Path, prefix: str) -> subprocess.CompletedProcess[str]:
        dotnet = shutil.which("dotnet")
        if dotnet is None:
            raise GenValConfigurationError(
                "dotnet runtime not found. Install .NET 8 SDK/runtime and build the "
                "NIST GenValAppRunner (scripts/nist/build_nist_genval.sh)."
            )
        if not self.settings.runner_dll.exists():
            raise GenValConfigurationError(
                f"NIST GenValAppRunner binary not found: {self.settings.runner_dll}. "
                "Set GENVAL_RUNNER_DLL and build it before enabling USE_NIST_GENVAL."
            )

        stdout_path = work_dir / f"{prefix}.stdout.txt"
        stderr_path = work_dir / f"{prefix}.stderr.txt"
        command = [dotnet, str(self.settings.runner_dll), *args]
        try:
            completed = subprocess.run(
                command,
                cwd=str(work_dir),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.settings.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout_path.write_text(exc.stdout or "", encoding="utf-8")
            stderr_path.write_text(exc.stderr or "", encoding="utf-8")
            raise GenValExecutionError(
                f"NIST GenValAppRunner timed out after {self.settings.timeout_seconds} seconds."
            ) from exc

        stdout_path.write_text(completed.stdout or "", encoding="utf-8")
        stderr_path.write_text(completed.stderr or "", encoding="utf-8")
        if completed.returncode != 0:
            if prefix == "validation" and (work_dir / "validation.json").exists():
                return completed
            detail = (completed.stderr or completed.stdout or "").strip()
            if "Orleans" in detail or "Connection" in detail or "Silo" in detail:
                detail = f"Orleans.ServerHost may not be running. {detail}"
            raise GenValExecutionError(
                f"NIST GenValAppRunner failed for {prefix} with exit code {completed.returncode}. {detail}"
            )
        return completed


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _require_file(path: Path) -> Path:
    if not path.exists():
        raise GenValArtifactError(f"Required NIST GenVal artifact is missing: {path}")
    return path
