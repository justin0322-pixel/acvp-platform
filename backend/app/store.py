"""In-memory state store for the prototype.

Replace with PostgreSQL + SQLAlchemy for deployment (see CLAUDE.md). The shapes
here intentionally mirror a persistent model so the swap is mechanical.
"""
from dataclasses import dataclass, field
from itertools import count
from typing import Any


@dataclass
class VectorSet:
    vs_id: int
    mode_folder: str          # e.g. "ML-KEM-keyGen-FIPS203"
    # generating: vectors not ready yet (GET returns retry) -> ready: prompt available ->
    # prompt_retrieved -> response_submitted -> disposition -> certified; expired is terminal.
    status: str = "generating"
    prompt: dict | None = None
    response: dict | None = None
    validation: dict | None = None
    resubmit_count: int = 0

    def disposition(self) -> str:
        """Map lifecycle state to an ACVP disposition value.

        Spec values: passed / fail / incomplete / unreceived / missing /
        expired / error. We synthesize unreceived/incomplete/expired/error from
        state; passed/fail come through from the crypto module's validation.
        """
        if self.status == "expired":
            return "expired"
        if self.validation is not None:
            return self.validation.get("disposition", "error")
        if self.status == "response_submitted":
            return "incomplete"  # responses received, validation in progress
        return "unreceived"      # no responses received yet


@dataclass
class TestSession:
    session_id: int
    vector_sets: list[VectorSet] = field(default_factory=list)
    passed: bool | None = None
    is_sample: bool = False
    encrypt_at_rest: bool = False
    publishable: bool = False
    created_on: str | None = None
    expires_on: str | None = None
    access_token: str | None = None


class Store:
    def __init__(self) -> None:
        self._sessions: dict[int, TestSession] = {}
        self._session_ids = count(1)
        self._vs_ids = count(1)
        self._requests: dict[int, dict[str, Any]] = {}
        self._request_ids = count(1)

    def create_session(self) -> TestSession:
        sid = next(self._session_ids)
        s = TestSession(session_id=sid)
        self._sessions[sid] = s
        return s

    def get_session(self, sid: int) -> TestSession | None:
        return self._sessions.get(sid)

    def add_vector_set(self, session: TestSession, mode_folder: str) -> VectorSet:
        vs = VectorSet(vs_id=next(self._vs_ids), mode_folder=mode_folder)
        session.vector_sets.append(vs)
        return vs

    def get_vector_set(self, session: TestSession, vs_id: int) -> VectorSet | None:
        return next((v for v in session.vector_sets if v.vs_id == vs_id), None)

    def new_request(self) -> int:
        rid = next(self._request_ids)
        self._requests[rid] = {"status": "processing", "location": None}
        return rid

    def get_request(self, rid: int) -> dict | None:
        return self._requests.get(rid)

    def complete_request(self, rid: int, location: str) -> None:
        self._requests[rid] = {"status": "approved", "location": location}


store = Store()
