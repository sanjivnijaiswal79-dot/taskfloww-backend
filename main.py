"""
Main FastAPI application entry point.

What's wired here
-----------------
1. Custom timing middleware — runs on EVERY request, logs method + path +
   elapsed milliseconds to stdout.
2. CORS middleware — allows requests from the frontend's local dev origin(s)
   with explicit allowed methods and headers (not left at framework defaults).
3. Database tables created at startup via create_tables().
4. The three feature routers registered with their /api/v1 prefix.
"""

import logging
import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from database import create_tables
from routers import nested, projects, tasks, users

# Load .env file (project root). Shell variables take precedence.
load_dotenv()

# ─── logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Custom timing middleware
# =============================================================================

class TimingMiddleware(BaseHTTPMiddleware):
    """
    Logs the HTTP method, URL path, response status code, and wall-clock
    processing time (in milliseconds) for every request.

    Example console output:
        2025-08-07T16:42:01  INFO      GET  /api/v1/tasks/  200  3.14 ms
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_ns  = time.perf_counter_ns()
        response  = await call_next(request)
        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000  # ns → ms

        logger.info(
            "%-7s %-40s  %d  %.2f ms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


# =============================================================================
# Application factory
# =============================================================================

def create_app() -> FastAPI:

    # ── 3. Lifespan: create DB tables on startup ──────────────────────────────
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        create_tables()
        logger.info("Database tables created / verified.")
        yield  # server runs here
        # (add teardown logic below yield if needed)

    app = FastAPI(
        title="Capstone Project API",
        description=(
            "FastAPI backend with SQLAlchemy ORM, full CRUD for users / projects / tasks, "
            "per-project statistics, timing middleware, and CORS."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── 1. Custom timing middleware ───────────────────────────────────────────
    # Registered BEFORE CORSMiddleware so the timer includes the full
    # request lifecycle; CORS preflight OPTIONS calls are also timed.
    app.add_middleware(TimingMiddleware)

    # ── 2. CORS middleware ────────────────────────────────────────────────────
    # Origins are read from ALLOWED_ORIGINS in .env (comma-separated).
    # Falls back to the common Live Server / Vite origins if the variable
    # is not set, so the app works out-of-the-box without any .env file.
    _origins_env = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,         # explicit list — not ["*"]
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # explicit
        allow_headers=[                        # explicit — not ["*"]
            "Content-Type",
            "Authorization",
            "Accept",
            "Origin",
            "X-Requested-With",
        ],
        expose_headers=["Content-Length"],
        max_age=600,                           # preflight cache: 10 minutes
    )

    # ── 4. Register routers ───────────────────────────────────────────────────
    app.include_router(users.router)
    app.include_router(projects.router)
    app.include_router(tasks.router)
    app.include_router(nested.router)

    # ── 5. Health-check ───────────────────────────────────────────────────────
    @app.get("/health", tags=["meta"], summary="Health check")
    def health() -> dict:
        return {"status": "ok"}

    return app


# ─── module-level app instance (used by uvicorn / gunicorn) ──────────────────
app = create_app()
