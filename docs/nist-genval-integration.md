# Connecting the real 203/204 crypto engine (NIST GenVal)

How to switch this server from the vendored NIST fixtures to the **real** crypto engine, and how to
accept all five modes. Our code is already "engine-ready" — connecting it is a build plus a config
flag, not a code change.

> **Flag for human review.** Everything here touches the crypto boundary. Do not auto-merge changes
> to `backend/app/crypto_boundary/`. No crypto math lives in this repo — we only exchange JSON files
> with the engine across a process boundary.

## What the engine is

Both the FIPS 203 (ML-KEM) and FIPS 204 (ML-DSA) teams wrap the **same** engine: the NIST
ACVP-Server **GenVal** app plus a **Microsoft Orleans** silo, C#/**.NET 8**. One engine serves all
five modes. It uses NIST's own reference crypto (not the .NET in-box `MLKem`), so it runs on
Linux/macOS; integration testing is cleanest in Docker.

The engine is **file/dir based** (not stdin/stdout):

| Step | Command | Reads | Writes (into the work dir) |
| --- | --- | --- | --- |
| check | `dotnet GenValApp.dll -c registration.json` | registration | — |
| generate | `dotnet GenValApp.dll -g registration.json` | registration | `prompt.json` + `internalProjection.json` + `expectedResults.json` |
| validate | `dotnet GenValApp.dll -n internalProjection.json -b response.json` | answer key + DUT response | `validation.json` |

`validation.json` shape is `{vsId, disposition, tests:[{tcId, result}]}` with
`disposition`/`result` ∈ `passed`/`failed` — exactly what `store.VectorSet.disposition()` consumes,
so no normalization layer is needed.

## Run the whole stack in Docker (one command)

`docker compose up --build` runs everything: a single **backend** container hosting the FastAPI app
**and** the NIST engine (Orleans silo + GenVal runner) on localhost, plus the **frontend**. The
backend defaults to `USE_NIST_GENVAL=true`, so it grades with the real engine out of the box.

**Prerequisite (one-time):** build the engine binaries into `backend/nist-bin/` first — the image
copies them (they are gitignored, so a fresh clone won't have them):

```bash
scripts/nist/build-genval.sh /path/to/ACVP-Server   # needs the .NET 8 SDK (see runbook below)
docker compose up --build                            # backend+engine on :8000, frontend on :5173
```

**Why one container (not an Orleans sidecar):** `OrleansSiloHost.cs` hardcodes
`AdvertisedIPAddress = IPAddress.Loopback` and `UseLocalhostClustering()`, so the silo is only
reachable on **localhost** — exactly how the 203/204 teams run it. The backend, silo, and runner
therefore share one container (`backend/docker/backend-entrypoint.sh` starts the silo, waits for its
gateway, then launches uvicorn). The silo port is moved off 8000 to avoid colliding with the API.
A future split into an Orleans sidecar would require patching that hardcoded address in the fork.

Verified in-container: real 5-mode grading works (correct answers → `passed`, corrupted → `failed`)
for both ML-KEM and ML-DSA. Set `USE_NIST_GENVAL=false` (compose env) for fixture-stub mode with no
engine (no `nist-bin/` needed).

## Build it yourself (runbook)

The FIPS 203 team's trimmed fork is the engine of record (gen-val reduced to ML-KEM/ML-DSA, its
`Directory.*.props` at the repo root so `dotnet publish` needs no config copy). Our
`scripts/nist/*` wrap the build/run.

```bash
# 0. Prereq: install the .NET 8 SDK (dotnet --version should print 8.x).
#    dotnet is often outside a non-login shell's PATH — if `which dotnet` is empty:
#      export PATH="/usr/local/share/dotnet:$PATH"

# 1. Clone the engine source (anywhere; a sibling dir is fine) and check out the PINNED commit.
#    The engine grades our vector sets, so it is pinned exactly like the golden vectors are —
#    build-genval.sh refuses to build anything else. The pin lives in that script.
git clone https://github.com/hhhylaiii/ACVP-Server.git ../ACVP-Server
git -C ../ACVP-Server checkout 61b549e51ca18c75c303cf83f6fb58f40c1de700

# 2. Publish the runner + Orleans host into backend/nist-bin/ (gitignored):
scripts/nist/build-genval.sh ../ACVP-Server        # or: NIST_SRC=../ACVP-Server scripts/nist/build-genval.sh
#    Writes backend/nist-bin/ENGINE_SOURCE.txt recording which commit the binaries came from.

# 3. Start Orleans in its own shell and leave it running:
scripts/nist/start-orleans.sh

# 4. Smoke-test the engine directly (from a scratch dir), before touching the server:
mkdir -p /tmp/gv && cd /tmp/gv
cp <repo>/tests/fixtures/nist/ML-DSA-keyGen-FIPS204/registration.json .
<repo>/scripts/nist/run-genval.sh generate registration.json          # -> prompt/internalProjection/expectedResults
<repo>/scripts/nist/run-genval.sh validate internalProjection.json expectedResults.json   # -> validation.json (disposition: passed)
```

Our provider calls the **published DLL directly** (`dotnet <GenValApp.dll> -c/-g/-n -b`); the FIPS 203
demo instead uses `dotnet run --project .../GenValAppRunner/src`. Both require Orleans running.

## Point this server at it

Set these in `backend/.env` (see `backend/.env.example`) and restart the API:

```bash
USE_NIST_GENVAL=true
GENVAL_RUNNER_DLL=<repo>/backend/nist-bin/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll
GENVAL_ARTIFACT_ROOT=<abs path for work dirs>   # optional; defaults to backend/data/acvp-sessions
GENVAL_TIMEOUT_SECONDS=120
```

With `USE_NIST_GENVAL=false` (default) the server stands in with the vendored fixtures and needs no
.NET — the whole pipeline still runs. If the engine or Orleans is misconfigured, generation/validation
surface as a vector-set disposition of `error` (details in the vector set's stored `error`), and the
provider annotates Orleans/connection failures.

### Automated acceptance against the real engine

Once built and Orleans is up, run the five-mode acceptance (golden → `passed`, corruption →
`failed`) without hand-driving the UI:

```bash
cd backend
ACVP_REAL_ENGINE=1 \
GENVAL_RUNNER_DLL=<repo>/backend/nist-bin/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll \
pytest tests/test_nist_real_engine.py -v
```

It skips unless `ACVP_REAL_ENGINE=1`, `dotnet` is installed, and the runner DLL exists — so it is
inert in normal CI. Generation goes through Orleans and can be slow; raise
`ACVP_REAL_ENGINE_TIMEOUT` (seconds) for the big signature modes.

## Accept all five modes

For each mode, drive the normal client flow (or the demo IUT) and confirm the disposition:

| Mode | FIPS | Expected |
| --- | --- | --- |
| ML-KEM keyGen | 203 | golden response → `passed` |
| ML-KEM encapDecap | 203 | golden response → `passed` |
| ML-DSA keyGen | 204 | golden response → `passed` |
| ML-DSA sigGen | 204 | golden response → `passed` |
| ML-DSA sigVer | 204 | golden response → `passed` |

Acceptance per mode (the golden-vector oracle): feed the engine a NIST `prompt` and the matching NIST
`expectedResults` as the response — it must reproduce NIST `validation` with `disposition: passed`.
Then corrupt one answer and resubmit — the disposition must flip to `failed`. This exact pass/fail
behavior is already proven on our code path (without .NET) by
`backend/tests/test_nist_end_to_end.py`, which routes the boundary through a fixture-backed fake
runner; against the real engine it becomes the formal acceptance run.

## Known limitations / risks

- **ML-DSA sigGen/sigVer registration fields.** The engine gates `externalMu` (internal interface)
  and `preHash` (external interface). Our mapper (`crypto_boundary/registration.py`) reproduces this;
  confirm the real engine accepts our envelopes for signature modes during acceptance.
- **ML-KEM encapsulation KAT.** The .NET path cannot inject the randomness `m`, so known-answer
  testing in the encapsulation direction is limited (tracked as a full-mode risk).
- **Orleans runtime weight.** The silo must be running and reachable; cold start is slow. Add a health
  check when containerizing (out of scope here).
- **Richer failure reporting (deferred).** `validation.json` carries only `{tcId, result}`. To show
  per-case group/expected/provided in the UI, join `tcId` back to the prompt/internalProjection (as
  the FIPS 204 team's normalizer does). Not required for correct disposition.
```
