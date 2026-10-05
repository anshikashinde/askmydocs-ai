from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.filings import router as filings_router
from app.api.health import router as health_router
from app.application.errors import ApplicationError, ResourceNotFoundError, UpstreamServiceError
from app.config import settings
from app.infrastructure.sec.client import SECClient
from app.logging_config import configure_logging

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.sec_client = SECClient(
        user_agent=settings.sec_user_agent,
        timeout_seconds=settings.sec_timeout_seconds,
    )
    yield
    application.state.sec_client.close()


app = FastAPI(
    title="AskMyDocs AI",
    version=settings.app_version,
    description="Foundation stage for a retrieval-augmented SEC filing analysis platform.",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(filings_router)


@app.exception_handler(ResourceNotFoundError)
async def not_found_error_handler(
    _request: object,
    exc: ResourceNotFoundError,
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(UpstreamServiceError)
async def upstream_error_handler(
    _request: object,
    exc: UpstreamServiceError,
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(ApplicationError)
async def application_error_handler(
    _request: object,
    exc: ApplicationError,
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unexpected_error_handler(
    _request: object,
    _exc: Exception,
) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
