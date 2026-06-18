from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.accepted_samples import router as accepted_samples_router
from app.api.auth import router as auth_router
from app.api.meta import router as meta_router
from app.api.transfers import router as transfers_router
from app.api.users import router as users_router
from app.core.config import settings
from app.services.model_runner import rewrite_text


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
def startup() -> None:
    if not settings.preload_lora_on_startup:
        return

    print("[startup] preloading LoRA model...")
    rewrite_text(
        source_text="我今天加班，可能晚点回去",
        role_code="boss",
        model_code="lora_finetuned",
    )
    print("[startup] LoRA model preload completed.")


app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(users_router, prefix="/api/users", tags=["users"])
app.include_router(meta_router, prefix="/api/meta", tags=["meta"])
app.include_router(transfers_router, prefix="/api/transfers", tags=["transfers"])
app.include_router(
    accepted_samples_router,
    prefix="/api/accepted-samples",
    tags=["accepted-samples"],
)
