from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import APP_NAME, CORS_ORIGINS
from .eval.routes import router as eval_router

app = FastAPI(
    title=f"{APP_NAME} API",
    description="工程规范智能问答平台 v1.0",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(eval_router)
app.include_router(eval_router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    return {"service": APP_NAME, "docs": "/docs"}
