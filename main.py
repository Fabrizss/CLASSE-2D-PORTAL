"""Deployment entry point for the FastAPI backend."""

import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "backend.server:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
    )
