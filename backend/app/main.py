from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import algorithms, login, metadata, requests, test_sessions, validations, vector_sets
from app.core.config import get_settings
from app.core.seed import seed_demo_metadata

app = FastAPI(title="ACVP server (server-client layer)", version="0.1.0")

seed_demo_metadata()

# mTLS enforcement — checks Nginx-forwarded client-cert headers when
# MTLS_ENABLED=true (ACVP spec §7.1). Must be added *before* CORS so
# Starlette runs CORS *before* mTLS in the middleware stack (outermost).
from app.core.tls import MTLSMiddleware  # noqa: E402
app.add_middleware(MTLSMiddleware)

# Allow the web client (dev server) to call the API from the browser.
# Added last so it's the outermost middleware, intercepting OPTIONS preflight
# and adding CORS headers to mTLS rejections.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    # TLS client certificates are credentials per the fetch spec: without
    # allow_credentials the browser drops responses to credentials:"include"
    # requests, and without that mode it opens a cert-less connection that
    # MTLSMiddleware rejects. Requires explicit origins (no "*"), which
    # cors_origins already is.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
app.include_router(metadata.router, prefix=API_PREFIX, tags=["metadata"])
app.include_router(vector_sets.router, prefix=API_PREFIX, tags=["vectorSets"])
app.include_router(requests.router, prefix=API_PREFIX, tags=["requests"])
app.include_router(validations.router, prefix=API_PREFIX, tags=["validations"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
