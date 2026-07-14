from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="Two Rivers Advisory — Close & Reconciliation Platform",
    description=(
        "Automated bank-to-GL reconciliation and trial-balance tie-out. "
        "Flags exactly which line items don't reconcile and why."
    ),
    version="0.1.0",
)
app.include_router(router)
