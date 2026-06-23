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


def submit(work: Callable[[int], Awaitable[None]]) -> int:
    """Register a request and run `work(request_id)` in the background."""
    rid = store.new_request()

    def runner() -> None:
        asyncio.run(work(rid))

    threading.Thread(target=runner, daemon=True).start()
    return rid
