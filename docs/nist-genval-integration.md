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

## Build the engine (on a .NET 8 host)

Use the FIPS 203 team's trimmed fork as the engine of record (gen-val reduced to ML-KEM/ML-DSA). The
203/204 repos ship the scripts; the essentials:

```bash
# 1. Get the NIST source (203 fork or the 204 team's vendored copy under third_party/)
# 2. Publish the runner + Orleans host with the .NET 8 SDK:
dotnet publish .../gen-val/samples/GenValAppRunner/src/NIST.CVP.ACVTS.Generation.GenValApp.csproj \
  -c Release -o ./.nist-bin/genval-runner
dotnet publish .../gen-val/samples/NIST.CVP.ACVTS.Orleans.ServerHost/...csproj \
  -c Release -o ./.nist-bin/orleans-server

# 3. Start Orleans in its own shell (leave it running):
dotnet ./.nist-bin/orleans-server/NIST.CVP.ACVTS.Orleans.ServerHost.dll --console
```

There are two invocation styles in the wild: our provider calls the **published DLL directly**
(`dotnet <GenValApp.dll> ...`, the FIPS 204 team's style); the FIPS 203 demo uses
`dotnet run --project .../GenValAppRunner/src` with a separately-running Orleans silo. Both need
Orleans up.

## Point this server at it

Set these (see `backend/.env.example`) and restart the API:

```bash
USE_NIST_GENVAL=true
GENVAL_RUNNER_DLL=/abs/path/.nist-bin/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll
GENVAL_ARTIFACT_ROOT=/abs/path/for/per-vector-set/work-dirs   # optional; defaults to backend/data/acvp-sessions
GENVAL_TIMEOUT_SECONDS=120
```

With `USE_NIST_GENVAL=false` (default) the server stands in with the vendored fixtures and needs no
.NET — the whole pipeline still runs. If the engine or Orleans is misconfigured, generation/validation
surface as a vector-set disposition of `error` (details in the vector set's stored `error`), and the
provider annotates Orleans/connection failures.

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
