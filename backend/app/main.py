import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.approval.admin_router import admin_router as approval_admin_router
from app.approval.router import router as approval_router
from app.approval.seed import initialize_approval_schema, seed_approval_demo_data
from app.core.config import settings
from app.core.logging import configure_logging, request_id_var
from app.db.seed import initialize_schema, seed_demo_data
from app.screening.router import router as screening_router

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_schema()
    initialize_approval_schema()
    if settings.should_seed_demo:
        seed_demo_data()
        seed_approval_demo_data()
        logger.info("startup: schema ready, demo data seeded (database=%s)", settings.database_mode)
    else:
        logger.info("startup: schema ready, demo seeding skipped (database=%s)", settings.database_mode)
    yield


def create_app() -> FastAPI:
    settings.validate_runtime_config()
    configure_logging(settings.log_level)
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Common foundation API for the four-in-one enterprise AI portfolio.",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=(
            r"http://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|"
            r"192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+):517[3-4]"
            if settings.app_env == "development"
            else None
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        token = request_id_var.set(request.state.request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.log(
                logging.WARNING if response.status_code >= 500 else logging.INFO,
                "%s %s -> %s %.1fms",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception("%s %s failed after %.1fms", request.method, request.url.path, elapsed_ms)
            raise
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    application.include_router(router, prefix=settings.api_v1_prefix)
    application.include_router(screening_router, prefix=settings.api_v1_prefix)
    application.include_router(approval_router)
    application.include_router(approval_admin_router)

    return application


app = create_app()
