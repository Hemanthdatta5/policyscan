"""Tracker audit worker: runs in its own container on an isolated network with no secrets
and no database access. The API calls POST /audit; the worker validates the URL itself.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.services.tracker_audit import AuditError, render_page, run_audit

app = FastAPI(title="PolicyScan audit worker", docs_url=None, openapi_url=None)


class AuditRequest(BaseModel):
    url: str = Field(max_length=2048)


@app.post("/audit")
def audit(req: AuditRequest) -> dict:
    try:
        return run_audit(req.url)
    except AuditError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/render")
def render(req: AuditRequest) -> dict:
    try:
        return render_page(req.url)
    except AuditError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
