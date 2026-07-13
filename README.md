# ACVP Validation Platform (Server-Client Protocol Layer)

This repository implements the **server-client (protocol) layer** of an Automated Cryptographic Validation Protocol (ACVP) platform, specifically targeting **FIPS 203 (ML-KEM)** and **FIPS 204 (ML-DSA)**.

For development process, sprint plans, and internal conventions, see:
* `docs/dev-process.md` (Sprint plans, architecture decisions, and checklists)
* `CLAUDE.md` (Working context)
* `.claude/skills/acvp-protocol/SKILL.md` (Protocol guardrails)

---

## 🏛️ Architecture & Tech Stack

* **Backend:** FastAPI (Python 3) + Pydantic v2 (ACVP JSON schema validation) + SQLite.
* **Frontend:** React + Vite + TypeScript + TanStack Query + Tailwind CSS.
* **Proxy / Security:** Nginx acting as an ACV Proxy, terminating TLS 1.2+ and enforcing mTLS (mutual TLS) authentication.
* **Crypto Boundary:** Calls the NIST ACVP-Server GenVal engine (C#/.NET 8, + Orleans) across a process boundary via its **file-based CLI** — `GenValApp.dll -g registration.json` to generate, `-n internalProjection.json -b response.json` to validate. Enable with `USE_NIST_GENVAL=true`; by default NIST golden fixtures stand in as a stub so the flow runs with no .NET.

---

## 🚀 Quick Start (Local Development)

### 1. Fetch NIST Golden Vectors
We use official NIST sample vectors to test the platform.
```bash
chmod +x scripts/fetch-nist-fixtures.sh
./scripts/fetch-nist-fixtures.sh
```

### 2. Run with Docker (Recommended)
This spins up the Nginx ACV Proxy (mTLS), FastAPI backend, and React frontend.
```bash
# Generate dev certificates for mTLS
./scripts/gen-certs.sh   # (or gen-certs.ps1 on Windows)

# Start all services
docker compose up --build
```
* **Frontend UI:** `https://localhost:8443`
* **API Docs:** `https://localhost:8443/docs`
* **Demo Password:** `acvp-demo` (defined in `backend/.env.example`)

### 3. Run Manually (Without Docker)

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                     # Run the test suite
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

---

## 🔒 Security & Authentication

This platform adheres to ACVP spec §7 and §12:
1. **mTLS (Mutual TLS):** Enforced via Nginx. Client certificates are verified before the request reaches the application.
2. **JWT (JSON Web Tokens):** Uses `HS256` for signing. A valid token must be obtained from `/login` and provided as a `Bearer` token in the `Authorization` header.
3. **TOTP (Upcoming):** True to NIST's production environment, the password payload can be configured to require a TOTP code. 

**Testing mTLS locally:**
```bash
curl --cacert backend/certs/ca.crt \
     --cert backend/certs/client.crt \
     --key backend/certs/client.key \
     https://localhost:8443/acvp/v1/algorithms
```
