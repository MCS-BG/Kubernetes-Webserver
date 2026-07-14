from pathlib import Path

from fastapi import FastAPI
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
app.include_router(router)
app.include_router(chat_router)

_web_dir = Path(__file__).resolve().parent.parent / "web"
if _web_dir.is_dir():
    app.mount("/app", StaticFiles(directory=_web_dir, html=True), name="web")
