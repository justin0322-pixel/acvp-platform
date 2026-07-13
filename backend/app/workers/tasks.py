"""arq worker definitions (deployment task queue).

The runnable scaffold uses app/core/jobs.py (in-process) so it needs no Redis. For
deployment, run an arq worker against these tasks and have the API submit to arq
instead of the in-process runner. Both call the same crypto_boundary functions.

    arq app.workers.tasks.WorkerSettings

These signatures MUST track crypto_boundary.client — they are not exercised by the
in-process path, so drift here stays invisible until deployment. test_worker_contract
binds them against the real client signatures to keep that from happening again.

[HUMAN REVIEW] crypto-boundary adjacent — do not auto-merge.
"""
from dataclasses import asdict

from app.crypto_boundary import client


async def generate(
    ctx: dict, registration: dict, mode_folder: str, *, session_id: int, vs_id: int
) -> dict:
    """Produce a vector set. Returns the GeneratedVectors fields (prompt /
    internal_projection / expected) as a dict, since arq must serialize the result."""
    return asdict(
        client.generate(registration, mode_folder, session_id=session_id, vs_id=vs_id)
    )


async def validate(
    ctx: dict,
    internal_projection: dict | None,
    response: dict,
    mode_folder: str,
    *,
    session_id: int,
    vs_id: int,
) -> dict:
    """Grade a submitted response. `internal_projection` is the answer key persisted
    at generation time — the NIST engine cannot validate without it."""
    return client.validate(
        internal_projection, response, mode_folder, session_id=session_id, vs_id=vs_id
    )


class WorkerSettings:
    functions = [generate, validate]
    # redis_settings = RedisSettings(...)  # configure for deployment
