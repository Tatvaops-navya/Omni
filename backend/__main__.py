"""Run the FastAPI app from the project root: python -m backend"""
from __future__ import annotations

import uvicorn

from backend.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.uvicorn_reload,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
