"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api import rest, ws

app = FastAPI(
    title="Poker Engine API",
    description="Event-sourced No-Limit Texas Hold'em poker engine",
    version="0.1.0",
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(rest.router)
app.include_router(ws.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Poker Engine API", "version": "0.1.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}

