"""Crypto-boundary provider: fixture fallback + NIST GenVal command wiring.

These exercise app/crypto_boundary WITHOUT a real .NET engine:
- the default (fixture) path still persists the answer key on the vector set, so
  the NIST validate path has what it needs once USE_NIST_GENVAL is enabled;
- NistCliGenValProvider constructs the documented `dotnet GenValApp -g / -n -b`
  commands (subprocess is faked);
- a missing runner DLL surfaces a clear GenValConfigurationError.
"""
import subprocess as _subprocess
import time
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.crypto_boundary.genval import (
    GenValConfigurationError,
    GenValSettings,
    NistCliGenValProvider,
)
from app.store import store

from helpers import registration, session_headers

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _register(client, v, auth_header):
    reg = [{"acvVersion": v}, {"algorithms": [registration("ML-KEM-keyGen-FIPS203")]}]
    r = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header)
    assert r.status_code == 200
    body = r.json()[1]
    return int(body["url"].rsplit("/", 1)[1]), body["vectorSetUrls"][0], session_headers(body)


def _vs(session_id, vs_url):
    return store.get_vector_set(store.get_session(session_id), int(vs_url.rsplit("/", 1)[1]))


# --- fixture (default) path -----------------------------------------------------

def test_fixture_path_persists_answer_key(client, acv_version, auth_header):
    sid, vs_url, sh = _register(client, acv_version, auth_header)
    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=sh).json()[1]:
            break
        time.sleep(0.02)
    vs = _vs(sid, vs_url)
    assert vs.prompt is not None
    # New: generation now persists internalProjection + expected on the vector set.
    assert vs.internal_projection is not None
    assert vs.expected is not None


# --- NIST GenVal command wiring (engine faked) ----------------------------------

def _fake_dotnet(monkeypatch, outputs: dict[str, str]) -> dict:
    """Fake `dotnet` + `subprocess.run`; the fake writes `outputs` into the cwd."""
    import app.crypto_boundary.genval.nist_cli_provider as mod

    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/dotnet")
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        wd = Path(kwargs["cwd"])
        for name, content in outputs.items():
            (wd / name).write_text(content)
        return _subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    return captured


def test_nist_generate_builds_g_command(monkeypatch, tmp_path):
    dll = tmp_path / "GenValApp.dll"
    dll.touch()
    settings = GenValSettings(runner_dll=dll, artifact_root=tmp_path, timeout_seconds=5)
    captured = _fake_dotnet(
        monkeypatch,
        {"prompt.json": "{}", "internalProjection.json": "{}", "expectedResults.json": "{}"},
    )
    work_dir = tmp_path / "wd"
    artifacts = NistCliGenValProvider(settings).generate({"algorithm": "ML-KEM"}, work_dir)

    cmd = captured["command"]
    assert cmd[0] == "/usr/bin/dotnet"
    assert cmd[1] == str(dll)
    assert cmd[2] == "-g"
    assert cmd[3].endswith("registration.json")
    assert artifacts.prompt.name == "prompt.json"
    assert artifacts.internal_projection.name == "internalProjection.json"
    assert artifacts.expected_results is not None


def test_nist_validate_builds_n_b_command(monkeypatch, tmp_path):
    dll = tmp_path / "GenValApp.dll"
    dll.touch()
    settings = GenValSettings(runner_dll=dll, artifact_root=tmp_path, timeout_seconds=5)
    captured = _fake_dotnet(monkeypatch, {"validation.json": '{"disposition": "passed"}'})
    work_dir = tmp_path / "wd"
    work_dir.mkdir()
    ip = work_dir / "internalProjection.json"
    ip.write_text("{}")
    resp = work_dir / "response.json"
    resp.write_text("{}")

    out = NistCliGenValProvider(settings).validate(ip, resp, work_dir)
    cmd = captured["command"]
    assert cmd[2] == "-n" and cmd[3].endswith("internalProjection.json")
    assert cmd[4] == "-b" and cmd[5].endswith("response.json")
    assert out.name == "validation.json"


def test_nist_provider_missing_runner_raises_config_error(tmp_path):
    settings = GenValSettings(
        runner_dll=tmp_path / "nope.dll", artifact_root=tmp_path, timeout_seconds=5
    )
    with pytest.raises(GenValConfigurationError):
        NistCliGenValProvider(settings).generate({"algorithm": "ML-KEM"}, tmp_path / "wd")
