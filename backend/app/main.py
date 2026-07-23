from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.approval.admin_router import admin_router as approval_admin_router
from app.approval.router import router as approval_router
from app.approval.seed import initialize_approval_db
from app.core.config import settings
from app.db.seed import initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    initialize_approval_db()
    yield


def create_app() -> FastAPI:
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
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    application.include_router(router, prefix=settings.api_v1_prefix)
    application.include_router(approval_router)
    application.include_router(approval_admin_router)

    return application


app = create_app()
