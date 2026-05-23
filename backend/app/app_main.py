from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from exceptions.base import APIException
from router import health_rt, run_rt
from utils.logger import bind_request_id, clear_request_id, configure_logging, get_logger
from utils.request_id import new_request_id, request_id_ctx

configure_logging()
log = get_logger("app_main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("service_start", service=settings.SERVICE_NAME, environment=settings.ENVIRONMENT)
    yield
    log.info("service_stop", service=settings.SERVICE_NAME)


app = FastAPI(
    title="RivalLens API",
    description="RivalLens walking skeleton backend.",
    version="0.1.0",
    lifespan=lifespan,
)

cors_allow_origins = [origin.strip() for origin in settings.CORS_ALLOW_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = new_request_id()
    token = request_id_ctx.set(request_id)
    bind_request_id()
    try:
        response = await call_next(request)
    finally:
        clear_request_id()
        request_id_ctx.reset(token)

    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(APIException)
async def api_exception_handler(_: Request, exc: APIException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_exception", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "Unexpected error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


app.include_router(health_rt.router)
app.include_router(run_rt.router)
