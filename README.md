# ACVP validation platform — server / client

The server-client (protocol) layer of an ACVP validation platform for FIPS 203 (ML-KEM)
and FIPS 204 (ML-DSA). The cryptography is owned by two separate teams and called as a
language-agnostic black box across a process boundary — this repo never implements crypto.

See `CLAUDE.md` for the working context, `.claude/skills/acvp-protocol/SKILL.md` for the
protocol rules, and `docs/dev-process.md` for the sprint plan and checklists.

## Quick start

```bash
# 1. Vendor the NIST golden test vectors (pinned; see tests/fixtures/nist/SOURCE.md)
chmod +x scripts/fetch-nist-fixtures.sh
scripts/fetch-nist-fixtures.sh

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                              # all green
uvicorn app.main:app --reload       # API + docs at http://localhost:8000/docs

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev                         # http://localhost:5173

# Or everything via Docker:
docker compose up --build
```

Demo login password is `acvp-demo` (see `backend/.env.example`).

## Keeping contributors human-only

This repo is configured so AI tooling does not appear in git attribution:
- `.claude/settings.json` blanks Claude Code's commit/PR attribution.
- `.githooks/commit-msg` strips any `Co-Authored-By` trailer as a backstop. Enable it once:
  ```bash
  git config core.hooksPath .githooks
  ```
- Commit under your own git identity (`git config user.name` / `user.email`).
