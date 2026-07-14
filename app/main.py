import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.chat.router import router as chat_router

app = FastAPI(
    title="Two Rivers Advisory — Close & Reconciliation Platform",
    description=(
        "Automated bank-to-GL reconciliation and trial-balance tie-out. "
        "Flags exactly which line items don't reconcile and why."
    ),
    version="0.1.0",
)

# Needed once the web widget is hosted separately from this API (e.g. widget
# on Azure Static Web Apps, API on Azure Container Apps) -- same-origin
# deployments (like /app/ below) don't need this at all. Empty by default:
# no cross-origin access until explicitly configured.
_allowed_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

app.include_router(router)
app.include_router(chat_router)

_web_dir = Path(__file__).resolve().parent.parent / "web"
if _web_dir.is_dir():
    app.mount("/app", StaticFiles(directory=_web_dir, html=True), name="web")
