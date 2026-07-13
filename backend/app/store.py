"""In-memory state store for the prototype.

Replace with PostgreSQL + SQLAlchemy for deployment (see CLAUDE.md). The shapes
here intentionally mirror a persistent model so the swap is mechanical.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import count
from typing import Any

# ACVP disposition vocabulary (spec messaging). The crypto engine (NIST GenVal)
# emits passed/failed at the vector-set and per-test-case level; we synthesize the
# rest from lifecycle state. Any disposition the engine returns outside this set is
# treated as `error` rather than passed through blindly.
DISPOSITIONS = frozenset(
    {"passed", "failed", "incomplete", "unreceived", "missing", "expired", "error"}
)


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
    missing_tc_ids: list[int] = field(default_factory=list)
    capabilities: dict | None = None   # validated registration capabilities
    registration: dict | None = None   # NIST-shaped registration for generate()
    internal_projection: dict | None = None  # answer key from generation; NIST validate needs it
    expected: dict | None = None       # expectedResults, disclosed only for isSample
    error: str | None = None           # set when generation/validation raised
    expires_at: datetime | None = None  # submission deadline (spec 14)

    def expired(self) -> bool:
        """True once the submission deadline has passed (spec 14).

        Derived from the clock rather than swept by a background job, so it is
        correct the moment it is asked. `status == "expired"` stays supported as
        an explicit terminal override.
        """
        if self.status == "expired":
            return True
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    def disposition(self) -> str:
        """Map lifecycle state to an ACVP disposition value (see DISPOSITIONS).

        We synthesize unreceived/incomplete/missing/expired/error from state;
        passed/failed come through from the crypto module's validation, normalized
        against the known vocabulary.
        """
        if self.status == "expired":
            return "expired"
        if self.status == "error":
            return "error"  # generation or validation failed (see self.error)
        if self.response is None and self.expired():
            # Spec: expired == the responses never arrived before the deadline. A
            # grade earned in time is not retroactively voided by the deadline.
            return "expired"
        if self.missing_tc_ids:
            return "missing"  # submission lacked some of the prompt's test cases
        if self.validation is not None:
            disposition = self.validation.get("disposition", "error")
            return disposition if disposition in DISPOSITIONS else "error"
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
        self._validations: dict[int, dict[str, Any]] = {}
        self._validation_ids = count(1)

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

    def add_validation(self, session_id: int, created_on: str) -> int:
        """Record a validation (certificate) resource produced by certification."""
        vid = next(self._validation_ids)
        self._validations[vid] = {"session_id": session_id, "created_on": created_on}
        return vid

    def get_validation(self, vid: int) -> dict | None:
        return self._validations.get(vid)


store = Store()
