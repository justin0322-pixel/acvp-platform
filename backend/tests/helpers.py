"""Shared test helpers for driving the result-submission flow."""
import json
import time

from app.core.config import get_settings
from app.store import store


def await_generation(session_id: int, vs_id: int, timeout: float = 5.0):
    """Block until the background generate task has settled; return the vector set.

    Generation runs on a real thread (app.core.jobs.run_background). A test that
    forces vectorSet state must let that thread finish first — otherwise the
    generator overwrites the forced state from under it and the test is racy.
    """
    vs = store.get_vector_set(store.get_session(session_id), vs_id)
    deadline = time.monotonic() + timeout
    while vs.status == "generating" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert vs.status != "generating", f"vector set {vs_id} never finished generating"
    return vs


def await_validation(session_id: int, vs_id: int, timeout: float = 5.0):
    """Block until the background validate task has settled; return the vector set.

    Same hazard as await_generation: a test that injects a crypto verdict onto the
    vector set must wait for the real validate thread to land first.
    """
    vs = store.get_vector_set(store.get_session(session_id), vs_id)
    deadline = time.monotonic() + timeout
    while vs.status not in ("disposition", "error") and time.monotonic() < deadline:
        time.sleep(0.01)
    assert vs.status in ("disposition", "error"), f"vector set {vs_id} was never validated"
    return vs


def session_headers(register_body: dict) -> dict:
    """Bearer header carrying a session's own accessToken (sub=session:{id}).

    Per spec, session-scoped operations must be authorized with the token the
    session was issued at registration, not the login token.
    """
    return {"Authorization": f"Bearer {register_body['accessToken']}"}


def golden_response(vs_id: int, mode_folder: str = "ML-KEM-keyGen-FIPS203") -> dict:
    """A valid client submission: the NIST golden answers, stamped with our vsId."""
    path = get_settings().fixtures_dir / mode_folder / "expectedResults.json"
    expected = json.loads(path.read_text())
    return {**expected, "vsId": vs_id}


def registration(mode_folder: str = "ML-KEM-keyGen-FIPS203") -> dict:
    """A valid capability registration: the NIST example for this mode."""
    path = get_settings().fixtures_dir / mode_folder / "registration.json"
    return json.loads(path.read_text())
