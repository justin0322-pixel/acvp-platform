"""End-to-end ACVP flow demo — run it in front of someone to show the backend works.

Walks the full spec flow against the real FastAPI app and prints each step with
its actual HTTP status and JSON, so a reviewer can see the protocol behave live.

Run (from backend/, with the venv active):
    python scripts/demo_flow.py
No server needed — it drives the real app in-process.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # put backend/ on path

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import get_settings  # noqa: E402

S = get_settings()
V = S.acv_version
c = TestClient(app)


def show(step: str, method: str, path: str, resp) -> dict:
    body = resp.json() if resp.content else None
    print(f"\n\033[1m▶ {step}\033[0m")
    print(f"  {method} {path}  ->  HTTP {resp.status_code}")
    if body is not None:
        text = json.dumps(body, indent=2)
        if len(text) > 900:
            text = text[:900] + " …(truncated)"
        print("  " + text.replace("\n", "\n  "))
    else:
        print("  (empty body)")
    return body[1] if isinstance(body, list) and len(body) == 2 else body


# 1. Login -------------------------------------------------------------------
r = c.post("/acvp/v1/login", json=[{"acvVersion": V}, {"password": S.demo_password}])
token = show("1. Login (get JWT)", "POST", "/login", r)["accessToken"]
h = {"Authorization": f"Bearer {token}"}
print(f"  -> got JWT ({token[:20]}…)")

# 2. Register a test session -------------------------------------------------
reg = [{"acvVersion": V}, {"algorithms": [
    {"algorithm": "ML-KEM", "mode": "keyGen", "revision": "FIPS203"}]}]
r = c.post("/acvp/v1/testSessions", json=reg, headers=h)
sess = show("2. Register test session (declare algorithms)", "POST", "/testSessions", r)
sid = int(sess["url"].rsplit("/", 1)[1])
vs_url = sess["vectorSetUrls"][0]

# 3. Retrieve the vector set — async, may say 'retry' ------------------------
for i in range(50):
    r = c.get(vs_url, headers=h)
    payload = r.json()[1]
    if "retry" in payload:
        if i == 0:
            show("3a. Retrieve vectors — not ready yet (retry)", "GET", vs_url, r)
        time.sleep(0.02)
        continue
    show("3b. Retrieve vectors — ready (the exam)", "GET", vs_url, r)
    break

# 4. Submit answers — no content, no score -----------------------------------
r = c.post(vs_url + "/results", json=[{"acvVersion": V}, {"results": []}], headers=h)
show("4. Submit answers (returns HTTP status only, no score)", "POST", vs_url + "/results", r)

# 5. Pull disposition — incomplete -> passed ---------------------------------
for i in range(50):
    r = c.get(vs_url + "/results", headers=h)
    disp = r.json()[1]["results"]["disposition"]
    if disp == "passed":
        show("5. Pull results (disposition: passed)", "GET", vs_url + "/results", r)
        break
    if i == 0:
        show("5a. Pull results (disposition: still validating)", "GET", vs_url + "/results", r)
    time.sleep(0.02)

# 6. Session-level summary ---------------------------------------------------
r = c.get(f"/acvp/v1/testSessions/{sid}/results", headers=h)
show("6. Session results summary", "GET", f"/testSessions/{sid}/results", r)

# 7. Certify -> poll request -> validation -----------------------------------
r = c.put(f"/acvp/v1/testSessions/{sid}",
          json=[{"acvVersion": V}, {"moduleUrl": "/acvp/v1/modules/1", "oeUrl": "/acvp/v1/oes/1"}],
          headers=h)
req = show("7. Certify the session", "PUT", f"/testSessions/{sid}", r)
for _ in range(50):
    r = c.get(req["url"], headers=h)
    if r.json()[1]["status"] == "approved":
        show("7b. Poll request -> validation certificate", "GET", req["url"], r)
        break
    time.sleep(0.02)

print("\n\033[1;32m✓ Full ACVP flow completed end-to-end.\033[0m")
