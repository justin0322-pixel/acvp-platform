"""Security demo — per-session authorization (the IDOR / BOLA fix, PR #3).

Shows that one tenant's session token cannot touch another tenant's session.
Run it in front of a reviewer:  python scripts/authz_demo.py
No server needed — it drives the real app in-process.

Before the fix, every line below returned HTTP 200 (a full cross-tenant breach).
After the fix, the whole attack surface returns 403; only the owner's own token works.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.config import get_settings  # noqa: E402

S = get_settings(); V = S.acv_version
c = TestClient(app)
G = "\033[32m"; R = "\033[31m"; B = "\033[1m"; DIM = "\033[2m"; X = "\033[0m"


def login() -> dict:
    tok = c.post("/acvp/v1/login", json=[{"acvVersion": V}, {"password": S.demo_password}]).json()[1]["accessToken"]
    return {"Authorization": f"Bearer {tok}"}


def register(login_hdr, *, sample: bool) -> dict:
    body = {"isSample": sample, "algorithms": [
        {"algorithm": "ML-KEM", "mode": "keyGen", "revision": "FIPS203", "parameterSets": ["ML-KEM-512"]}]}
    return c.post("/acvp/v1/testSessions", json=[{"acvVersion": V}, body], headers=login_hdr).json()[1]


def line(desc: str, resp):
    ok = resp.status_code == 403
    verdict = f"{G}BLOCKED{X}" if ok else f"{R}LEAKED{X}"
    print(f"    {desc:<46} HTTP {resp.status_code}   {verdict}")


print(f"\n{B}Per-session authorization demo{X}  {DIM}(ACVP · PR #3){X}")

# Two independent tenants each create a session with the same login.
lh = login()
A = register(lh, sample=False)          # attacker's own session
B_ = register(lh, sample=True)          # victim's session (sample → has an answer key)
a = {"Authorization": f"Bearer {A['accessToken']}"}       # attacker's session token
b = {"Authorization": f"Bearer {B_['accessToken']}"}      # victim's own token
aid = A["url"].rsplit("/", 1)[1]; bid = B_["url"].rsplit("/", 1)[1]; bvs = B_["vectorSetUrls"][0]

print(f"\n  Vendor A owns session {B}#{aid}{X};  Vendor B owns session {B}#{bid}{X} (a sample run).")
print(f"\n{B}  1) Attack: Vendor A uses its own session #{aid} token against Vendor B's session #{bid}{X}")
line(f"read session #{bid} details", c.get(f"/acvp/v1/testSessions/{bid}", headers=a))
line(f"list session #{bid} vector sets", c.get(f"/acvp/v1/testSessions/{bid}/vectorSets", headers=a))
line(f"download session #{bid} exam (prompt)", c.get(bvs, headers=a))
line(f"steal session #{bid} sample answer key", c.get(bvs + "/expected", headers=a))
line(f"tamper: submit answers for #{bid}", c.post(bvs + "/results", json=[{"acvVersion": V}, {"vsId": 1, "testGroups": []}], headers=a))
line(f"certify session #{bid} on B's behalf", c.put(f"/acvp/v1/testSessions/{bid}", json=[{"acvVersion": V}, {"moduleUrl": "/m", "oeUrl": "/o"}], headers=a))

print(f"\n{B}  2) Control: Vendor B uses its OWN session #{bid} token{X}")
r = c.get(f"/acvp/v1/testSessions/{bid}", headers=b)
print(f"    {'read own session #' + bid:<46} HTTP {r.status_code}   {G}OK{X}" if r.status_code == 200
      else f"    unexpected: {r.status_code}")

print(f"\n{DIM}  Spec basis: the accessToken issued per test session MUST be supplied to access that\n"
      f"  Test Session (11-messaging jwtToken). Before PR #3, every attack line above returned 200.{X}\n")
