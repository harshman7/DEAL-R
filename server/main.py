"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(
    title="Poker Engine API",
    description="Event-sourced No-Limit Texas Hold'em poker engine",
    version="0.1.0",
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Poker Engine API", "version": "0.1.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}

