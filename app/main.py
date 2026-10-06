from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.db import models

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
SETTINGS = get_settings()

if SETTINGS.env != "dev" and SETTINGS.secret_key in ("", "change-me"):
    raise RuntimeError("Set POLICYSCAN_SECRET_KEY to a long random value outside dev.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.init_db()
    db = next(models.get_db())
    try:
        models.purge_unsaved(db)
    finally:
        db.close()
    yield


app = FastAPI(title="PolicyScan", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # CSRF defence in depth: reject cross-origin state-changing requests (SameSite is the main defence).
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Cross-origin request blocked."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# Added after the header middleware so it runs first (outermost) and request.session exists.
app.add_middleware(
    SessionMiddleware,
    secret_key=SETTINGS.secret_key,
    session_cookie="policyscan_session",
    max_age=14 * 24 * 3600,
    same_site="lax",
    https_only=SETTINGS.env != "dev",
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
