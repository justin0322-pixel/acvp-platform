"""A fixture-backed stand-in for the NIST GenValApp .NET runner.

It mimics the runner's CLI so tests can exercise the *real* crypto-boundary code
path (client._nist_generate/_nist_validate -> NistCliGenValProvider._run ->
subprocess.run) without .NET installed:

  -c registration.json                       -> exit 0 (registration accepted)
  -g registration.json                       -> copy the mode's NIST fixtures
                                                (prompt/internalProjection/expectedResults)
                                                into the cwd (work dir)
  -n internalProjection.json -b response.json -> grade the response against the
                                                mode's expectedResults and write
                                                validation.json {vsId, disposition, tests}

Grading is exact-equality per test case (the golden response is a copy of
expectedResults, so it passes; any mutated field fails that case). Stdlib only —
this runs as a subprocess, not imported by pytest.
"""
import json
import os
import sys
from pathlib import Path


def _load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def _fixtures_root() -> Path:
    override = os.environ.get("FIXTURES_DIR_OVERRIDE")
    if override:
        return Path(override)
    # backend/tests/fake_genval_runner.py -> repo root / tests / fixtures / nist
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "nist"


def _folder_for(obj: dict) -> Path:
    name = f"{obj['algorithm']}-{obj['mode']}-{obj['revision']}"
    return _fixtures_root() / name


def _generate(registration_path: str, work_dir: Path) -> None:
    registration = _load(registration_path)
    src = _folder_for(registration)
    for name in ("prompt.json", "internalProjection.json", "expectedResults.json"):
        f = src / name
        if f.exists():
            (work_dir / name).write_text(f.read_text())


def _case_map(payload: dict) -> dict:
    return {
        (group.get("tgId"), test["tcId"]): {k: v for k, v in test.items() if k != "tcId"}
        for group in payload.get("testGroups", [])
        for test in group.get("tests", [])
    }


def _validate(internal_projection_path: str, response_path: str, work_dir: Path) -> None:
    internal_projection = _load(internal_projection_path)
    expected = _load(_folder_for(internal_projection) / "expectedResults.json")
    response = _load(response_path)

    expected_cases = _case_map(expected)
    response_cases = _case_map(response)

    tests = []
    all_passed = True
    for key, exp in expected_cases.items():
        ok = response_cases.get(key) == exp
        all_passed = all_passed and ok
        tests.append({"tcId": key[1], "result": "passed" if ok else "failed"})

    validation = {
        "vsId": internal_projection.get("vsId"),
        "disposition": "passed" if all_passed else "failed",
        "tests": sorted(tests, key=lambda t: t["tcId"]),
    }
    (work_dir / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")


def main(argv: list[str]) -> int:
    work_dir = Path.cwd()
    if not argv:
        return 2
    if argv[0] == "-c":
        return 0
    if argv[0] == "-g" and len(argv) == 2:
        _generate(argv[1], work_dir)
        return 0
    if argv[0] == "-n" and "-b" in argv:
        internal_projection = argv[1]
        response = argv[argv.index("-b") + 1]
        _validate(internal_projection, response, work_dir)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
