# CLAUDE.md — ACVP validation platform (server-client)

Project context for Claude Code. Read this first; it describes the repo as it is. The reusable
protocol rules live in the `acvp-protocol` skill (`.claude/skills/acvp-protocol/SKILL.md`), which
loads automatically — follow it whenever touching ACVP protocol, authentication, or fixtures.

## What this repo is

An ACVP validation platform for FIPS 203 (ML-KEM) and FIPS 204 (ML-DSA). This repo is the
**server-client / protocol layer**. The cryptography is owned by two separate teams and is called
as a language-agnostic black box across a process boundary — we never implement or verify crypto
math here. (Full rationale + boundary rules: the acvp-protocol skill.)

Protocol spec: https://pages.nist.gov/ACVP/ (`draft-fussell-acvp-spec`), pinned to ACVP 1.0.

## Tech stack

Backend
- FastAPI (REST + async) + Pydantic v2 (ACVP JSON schema models)
- uvicorn (ASGI), arq (task queue for the generate/validate crypto calls), PyJWT (HS256)
- SQLite for local dev, PostgreSQL for deployment

Frontend
- React + Vite + TypeScript
- TanStack Query (polling for the request-retry loop), Tailwind + shadcn/ui

Shared types: FastAPI's generated OpenAPI → `openapi-typescript` → frontend TS client.

## Repo layout

```
.
├── CLAUDE.md
├── .claude/skills/acvp-protocol/SKILL.md   protocol rules + guardrails (auto-loaded)
├── docs/dev-process.md                     full sprint plan + checklists
├── tests/fixtures/nist/                    READ-ONLY golden vectors + SOURCE.md
├── scripts/fetch-nist-fixtures.sh          vendors the fixtures
├── backend/
│   ├── app/
│   │   ├── main.py                FastAPI app + router wiring
│   │   ├── api/                   routers: login, test_sessions, vector_sets, requests, algorithms
│   │   ├── models/                Pydantic: envelope, registration, prompt, response, validation
│   │   ├── core/                  config, jwt/auth, security
│   │   ├── db/                    models + session
│   │   ├── workers/               arq tasks: generate, validate
│   │   └── crypto_boundary/       process-boundary client to the FIPS 203/204 module
│   ├── tests/                     pytest (conftest resolves repo-root tests/fixtures/nist)
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   └── package.json
└── docker-compose.yml
```

## Common commands

First run — vendor the golden vectors:
```bash
scripts/fetch-nist-fixtures.sh
```

Backend (from `backend/`):
```bash
python -m venv .venv && source .venv/bin/activate    # or: uv venv && source .venv/bin/activate
pip install -e ".[dev]"                              # or: uv sync
uvicorn app.main:app --reload                        # API on :8000
arq app.workers.tasks.WorkerSettings                 # task worker (deployment; needs Redis)
pytest                                               # run tests
```

Frontend (from `frontend/`):
```bash
npm install
npm run dev        # Vite dev server
npm run test       # vitest
npm run build
```

Everything together:
```bash
docker compose up --build
```

## Working conventions

- **Test-driven against the NIST fixtures.** For any endpoint or mode, read the fixtures under
  `tests/fixtures/nist/<MODE>/`, write a failing pytest first, then implement to green. Run
  `pytest` after every change. Fixtures are READ-ONLY — fix the code, never the fixture.
- **Fixtures are payloads, not wire messages.** A fixture is the inner object; the server wraps it
  in the `[{"acvVersion": "1.0"}, {payload}]` envelope. See `tests/fixtures/nist/SOURCE.md`.
- **One endpoint (or one cohesive unit) per PR.** Small, reviewable diffs.
- **Conventional commits** — `feat(login): ...`, `fix(vectorsets): ...`, `test(requests): ...`.
- **Do not implement crypto.** ML-KEM / ML-DSA math belongs to the 203/204 teams; call them across
  the process boundary in `app/crypto_boundary/`. Stub with NIST fixtures until the real module lands.
- **Flag auth/crypto-adjacent code for human review; never auto-merge it.** JWT must use HS256,
  never `alg: none`. Secrets never enter the repo (`.env.example` holds placeholders only).

## Git / commits

- Commit under a human git identity; this repo's contributors must stay human-only.
- Do NOT add a `Co-Authored-By:` trailer or any AI-attribution line to commits or PR bodies.
  (Enforced by `.claude/settings.json` `attribution` and the `.githooks/commit-msg` hook — this
  line is the version-independent backstop. Enable the hook once: `git config core.hooksPath .githooks`.)
- Conventional commits, one cohesive unit per commit.

## Current status / open dependencies

- The FIPS 203/204 teams' implementation **language is not yet decided**. This does NOT block us:
  the crypto boundary is a JSON-in / JSON-out process call, so their language is transparent. Build
  against the NIST fixtures as stubs — B0–B4 in the sprint plan need no crypto-team input.
- The generate/validate JSON contract (sprint task I0) is the first cross-team deliverable; the
  fixtures' schema IS that contract. See `docs/dev-process.md`.

## Pointers

- Protocol rules and guardrails: `.claude/skills/acvp-protocol/SKILL.md`
- Sprint plan, checklists, milestones, acceptance criteria: `docs/dev-process.md`
- Golden vectors + provenance: `tests/fixtures/nist/` and `tests/fixtures/nist/SOURCE.md`
- Spec: https://pages.nist.gov/ACVP/
