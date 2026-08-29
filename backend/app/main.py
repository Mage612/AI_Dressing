from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import health, styling, upload
from app.settings import DEV_ORIGINS, UPLOAD_DIR


app = FastAPI(title="衣渐佳 Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(health.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(styling.router, prefix="/api")
