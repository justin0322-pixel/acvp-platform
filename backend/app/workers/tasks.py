"""arq worker definitions (deployment task queue).

The runnable scaffold uses app/core/jobs.py (in-process) so it needs no Redis. For
deployment, run an arq worker against these tasks and have the API submit to arq
instead of the in-process runner. Both call the same crypto_boundary functions.

    arq app.workers.tasks.WorkerSettings
"""
from app.crypto_boundary import client


async def generate(ctx: dict, mode_folder: str) -> dict:
    return client.generate(mode_folder)


async def validate(ctx: dict, mode_folder: str, response: dict) -> dict:
    return client.validate(mode_folder, response)


class WorkerSettings:
    functions = [generate, validate]
    # redis_settings = RedisSettings(...)  # configure for deployment
