import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_v1_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.db.database import init_db
from app.services.ws_market_hub import ws_market_hub


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    init_db()
    logger = get_logger("qazan.startup")
    settings = get_settings()
    ws_market_hub.start()
    logger.info(
        "Started %s (%s) in %s mode",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.APP_ENV,
    )
    yield
    await ws_market_hub.stop()
    logger.info("Shutting down %s", settings.APP_NAME)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Open-source intelligent trading and market analysis backend.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = str(duration_ms)
        return response

    register_exception_handlers(app)
    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
