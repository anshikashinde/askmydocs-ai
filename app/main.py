from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.application.errors import ApplicationError
from app.config import settings
from app.logging_config import configure_logging

configure_logging(settings.log_level)

app = FastAPI(
    title="AskMyDocs AI",
    version=settings.app_version,
    description="Foundation stage for a retrieval-augmented SEC filing analysis platform.",
)

app.include_router(health_router)


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
