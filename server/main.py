"""FastAPI application entry point."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from server.api import auth, rest, ws
from server.config import settings
from server.middleware import logging as logging_middleware_module
from server.middleware import rate_limit
from server.persistence.event_store import EventStore

app = FastAPI(
    title="Poker Engine API",
    description="Event-sourced No-Limit Texas Hold'em poker engine",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add middleware (order matters!)
app.middleware("http")(logging_middleware_module.logging_middleware)
app.middleware("http")(rate_limit.rate_limit_middleware)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(rest.router)
app.include_router(ws.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    import traceback

    logger = logging_middleware_module.logger
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
        traceback=traceback.format_exc(),
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.get("/")
async def root():
    """Root endpoint - redirects to home or shows API info."""
    from fastapi.responses import RedirectResponse

    try:
        import os

        web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
        if os.path.exists(web_dir):
            return RedirectResponse(url="/web/home.html")
    except Exception:
        pass
    return {
        "message": "Poker Engine API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


# Serve web UI
try:
    import os

    web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
    if os.path.exists(web_dir):
        app.mount("/web", StaticFiles(directory=web_dir, html=True), name="web")
except Exception:
    pass  # Web directory might not exist


@app.get("/health")
async def health():
    """Enhanced health check endpoint."""
    from sqlalchemy import text

    # Check database connectivity
    db_healthy = False
    try:
        event_store = EventStore(settings.database_url)
        db = event_store.SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_healthy = True
    except Exception as e:
        db_error = str(e)
    else:
        db_error = None

    status_code = 200 if db_healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if db_healthy else "unhealthy",
            "database": "connected" if db_healthy else "disconnected",
            "database_error": db_error,
            "version": "0.1.0",
        },
    )
