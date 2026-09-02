from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import health, styling, upload
from app.settings import DEV_ORIGINS, UPLOAD_DIR


FRONTEND_INDEX = Path(__file__).resolve().parents[2] / "index.html"


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


@app.get("/", include_in_schema=False)
def serve_frontend() -> FileResponse:
    return FileResponse(FRONTEND_INDEX)


@app.get("/index.html", include_in_schema=False)
def serve_frontend_index() -> FileResponse:
    return FileResponse(FRONTEND_INDEX)
