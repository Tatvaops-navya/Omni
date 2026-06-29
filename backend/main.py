"""
Aadhya – FastAPI Application Entry Point
Registers all routers and serves the admin UI static files at /krsna.
"""
from __future__ import annotations
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.agents.chat.whatsapp_handler import router as whatsapp_router
from backend.agents.voice.vapi_handler import router as vapi_router
from backend.admin.router import router as admin_router
from backend.admin.crm_router import router as crm_router
from backend.media.router import router as media_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Aadhya AI Omnichannel Lead Qualification System - Starting up")
    print("   Gemini intelligence: ready")
    print("   WhatsApp webhook: /webhook/whatsapp")
    print("   Vapi webhook: /webhook/vapi")
    print("   Admin panel: /krsna")
    yield
    print("Aadhya shutting down")


app = FastAPI(
    title="Aadhya – AI Interior Design Consultant",
    description="TatvaOps dual-channel AI consulting system (WhatsApp + Voice)",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=_settings.cors_origins_list != ["*"],  # credentials only when origins are restricted
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Agent Webhooks ────────────────────────────────────────────────────────────
app.include_router(whatsapp_router)
app.include_router(vapi_router)

# ─── Admin API ─────────────────────────────────────────────────────────────────
app.include_router(admin_router)
app.include_router(crm_router)
app.include_router(media_router)

# ─── Admin UI Static Files ─────────────────────────────────────────────────────
ADMIN_BUILD_DIR = Path(__file__).parent.parent / "admin-ui" / "dist"
if ADMIN_BUILD_DIR.exists():
    app.mount("/krsna", StaticFiles(directory=str(ADMIN_BUILD_DIR), html=True), name="krsna")
else:
    # During development, show a placeholder
    @app.get("/krsna")
    async def krsna_placeholder():
        return JSONResponse({
            "message": "Admin UI not built yet.",
            "instructions": "cd admin-ui && npm install && npm run build",
            "dev_mode": "cd admin-ui && npm run dev (runs on :5173)"
        })

# ─── Root ──────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "service": "Aadhya AI Interior Design Consultant",
        "version": "1.0.0",
        "company": "TatvaOps",
        "status": "operational",
        "endpoints": {
            "whatsapp_webhook": "/webhook/whatsapp",
            "vapi_webhook": "/webhook/vapi",
            "admin_panel": "/krsna",
            "admin_api": "/admin",
            "docs": "/docs",
        }
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aadhya"}
