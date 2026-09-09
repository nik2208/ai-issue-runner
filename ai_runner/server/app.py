"""FastAPI Application for the AI Issue Runner daemon."""

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from ai_runner.server.routes.auth import router as auth_router
from ai_runner.server.routes.jobs import router as jobs_router
from ai_runner.server.routes.webhook import router as webhook_router
from ai_runner.server.routes.ws import router as ws_router

def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Issue Runner",
        description="Decentralized AI Runner with Guarded Agentic Loop",
        version="0.1.0"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routes
    app.include_router(auth_router)
    app.include_router(jobs_router)
    app.include_router(webhook_router)
    app.include_router(ws_router)

    # Mount static dashboard files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app

app = create_app()
