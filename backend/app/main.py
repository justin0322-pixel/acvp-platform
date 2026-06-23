from fastapi import FastAPI

from app.api import algorithms, login, requests, test_sessions, vector_sets

app = FastAPI(title="ACVP server (server-client layer)", version="0.1.0")

API_PREFIX = "/acvp/v1"

app.include_router(login.router, prefix=API_PREFIX, tags=["auth"])
app.include_router(algorithms.router, prefix=API_PREFIX, tags=["algorithms"])
app.include_router(test_sessions.router, prefix=API_PREFIX, tags=["testSessions"])
app.include_router(vector_sets.router, prefix=API_PREFIX, tags=["vectorSets"])
app.include_router(requests.router, prefix=API_PREFIX, tags=["requests"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
