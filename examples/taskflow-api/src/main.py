"""TaskFlow API — main application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.auth.router import router as auth_router
from src.tasks.router import router as tasks_router
from src.notifications.router import router as notif_router
from src.billing.router import router as billing_router

app = FastAPI(title="TaskFlow API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9002"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
app.include_router(notif_router, prefix="/notifications", tags=["notifications"])
app.include_router(billing_router, prefix="/billing", tags=["billing"])


@app.get("/health")
def health():
    return {"status": "ok"}
