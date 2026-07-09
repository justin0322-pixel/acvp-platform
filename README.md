# ACVP validation platform — server / client

The server-client (protocol) layer of an ACVP validation platform for FIPS 203 (ML-KEM)
and FIPS 204 (ML-DSA). The cryptography is owned by two separate teams and called as a
language-agnostic black box across a process boundary — this repo never implements crypto.

See `CLAUDE.md` for the working context, `.claude/skills/acvp-protocol/SKILL.md` for the
protocol rules, and `docs/dev-process.md` for the sprint plan and checklists.

## Quick start

### Unix/macOS

```bash
# 1. Vendor the NIST golden test vectors (pinned; see tests/fixtures/nist/SOURCE.md)
chmod +x scripts/fetch-nist-fixtures.sh
scripts/fetch-nist-fixtures.sh

# 2. Backend (Terminal 1)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                              # all green
uvicorn app.main:app --reload       # API + docs at http://localhost:8000/docs

# 3. Frontend (Terminal 2)
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

### Windows (PowerShell)

```powershell
# 1. Backend (Terminal 1)
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
.\.venv\Scripts\pytest              # run backend tests
.\.venv\Scripts\uvicorn app.main:app --reload

# 2. Frontend (Terminal 2)
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

### Docker (Alternative)

```bash
docker compose up --build
```

Demo login password is `acvp-demo` (see `backend/.env.example`).
