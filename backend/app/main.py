from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import algorithms, login, requests, test_sessions, vector_sets

app = FastAPI(title="ACVP server (server-client layer)", version="0.1.0")


# ACVP errors carry an "error" field describing the problem (spec Appendix B),
# not FastAPI's default "detail". Render all errors in that shape.
@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "incorrectly formatted request body"},
    )


API_PREFIX = "/acvp/v1"

app.include_router(login.router, prefix=API_PREFIX, tags=["auth"])
app.include_router(algorithms.router, prefix=API_PREFIX, tags=["algorithms"])
app.include_router(test_sessions.router, prefix=API_PREFIX, tags=["testSessions"])
app.include_router(vector_sets.router, prefix=API_PREFIX, tags=["vectorSets"])
app.include_router(requests.router, prefix=API_PREFIX, tags=["requests"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
