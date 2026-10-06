import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    EMAIL_RE,
    MIN_PASSWORD_LENGTH,
    client_ip,
    hash_password,
    rate_limit_general,
    rate_limit_scan,
    verify_password,
)
from app.db.models import AuditLog, Report, User, get_db
from app.services import scan

router = APIRouter(prefix="/api", dependencies=[Depends(rate_limit_general)])

# Hash checked when the email is unknown, so login time does not reveal which emails exist.
_DUMMY_HASH = hash_password("not-a-real-password")


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)


class ScanRequest(BaseModel):
    url: str | None = Field(default=None, max_length=2048)
    text: str | None = Field(default=None, max_length=200_000)

    @model_validator(mode="after")
    def exactly_one(self):
        if bool(self.url) == bool(self.text):
            raise ValueError("provide either url or text")
        return self


def log(db: Session, request: Request, action: str, detail: str = "") -> None:
    db.add(AuditLog(user_id=request.session.get("uid"), ip=client_ip(request), action=action, detail=detail[:512]))
    db.commit()


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("uid")
    return db.get(User, uid) if uid else None


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Log in to do that.")
    return user


@router.post("/auth/register", status_code=201)
def register(body: Credentials, request: Request, db: Session = Depends(get_db)) -> dict:
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    if len(body.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(422, f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "That email is already registered.") from None
    request.session.clear()
    request.session["uid"] = user.id
    log(db, request, "register")
    return {"email": user.email}


@router.post("/auth/login")
def login(body: Credentials, request: Request, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    ok = verify_password(user.password_hash if user else _DUMMY_HASH, body.password)
    if not (user and ok):
        log(db, request, "login_failed")
        raise HTTPException(401, "Wrong email or password.")
    request.session.clear()  # new session on login
    request.session["uid"] = user.id
    log(db, request, "login")
    return {"email": user.email}


@router.post("/auth/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/auth/me")
def me(user: User | None = Depends(current_user)) -> dict:
    return {"email": user.email if user else None}


@router.post("/scan", dependencies=[Depends(rate_limit_scan)])
def run_scan(body: ScanRequest, request: Request, db: Session = Depends(get_db), user: User | None = Depends(current_user)) -> dict:
    try:
        result = scan.scan_url(body.url.strip()) if body.url else scan.scan_text(body.text)
    except scan.ScanError as exc:
        raise HTTPException(422, str(exc)) from exc
    report = Report(
        user_id=user.id if user else None,
        target=(body.url or "pasted text")[:2048],
        score=result["score"],
        rating=result["rating"],
        data=json.dumps(result),
    )
    db.add(report)
    db.commit()
    log(db, request, "scan", report.target)
    return report.payload()


def _owned_report(report_id: str, db: Session, user: User | None) -> Report:
    report = db.get(Report, report_id)
    if report is None or (report.user_id is not None and (user is None or report.user_id != user.id)):
        raise HTTPException(404, "Report not found.")
    return report


@router.get("/reports")
def list_reports(user: User = Depends(require_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(Report).where(Report.user_id == user.id, Report.saved.is_(True)).order_by(Report.created_at.desc()).limit(100)
    )
    return [
        {"id": r.id, "target": r.target, "score": r.score, "rating": r.rating, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@router.get("/reports/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db), user: User | None = Depends(current_user)) -> dict:
    return _owned_report(report_id, db, user).payload()


@router.post("/reports/{report_id}/save")
def save_report(report_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    report = _owned_report(report_id, db, user)
    report.user_id = user.id
    report.saved = True
    db.commit()
    return report.payload()


@router.delete("/reports/{report_id}")
def delete_report(report_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)) -> dict:
    report = _owned_report(report_id, db, user)
    if report.user_id != user.id:
        raise HTTPException(404, "Report not found.")
    db.delete(report)
    db.commit()
    return {"ok": True}
