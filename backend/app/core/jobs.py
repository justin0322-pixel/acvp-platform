"""In-process async job runner for the request-retry pattern.

Runs background work without external infrastructure so the scaffold is runnable
out of the box. For deployment, swap this for arq (see app/workers/tasks.py) — the
endpoints only depend on `submit()` returning a request id and the store being
updated on completion.
"""
import asyncio
import threading
from collections.abc import Awaitable, Callable

from app.store import store


def submit(work: Callable[[int], Awaitable[None]], *, owner: str | None = None) -> int:
    """Register a request and run `work(request_id)` in the background.

    For work polled via `GET /requests/{id}` (e.g. response validation). `owner` is
    the JWT subject the request belongs to; it scopes the request listing.
    """
    rid = store.new_request(owner)

    def runner() -> None:
        asyncio.run(work(rid))

    threading.Thread(target=runner, daemon=True).start()
    return rid


def run_background(work: Callable[[], Awaitable[None]]) -> None:
    """Run `work()` in the background without a request handle.

    For vector-set generation, which the client polls via the vectorSet GET
    (the `retry` response) rather than via the request-retry endpoint — these
    are two distinct polling points in the spec.
    """

    def runner() -> None:
        asyncio.run(work())

    threading.Thread(target=runner, daemon=True).start()
