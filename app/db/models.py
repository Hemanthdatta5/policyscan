import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    delete,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    target: Mapped[str] = mapped_column(String(2048))
    score: Mapped[float] = mapped_column(Float)
    rating: Mapped[str] = mapped_column(String(16))
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    data: Mapped[str] = mapped_column(Text)

    def payload(self) -> dict:
        return {**json.loads(self.data), "id": self.id, "saved": self.saved, "created_at": self.created_at.isoformat()}


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(String(512), default="")


_engine = None
_Session = None


def init_db(url: str | None = None) -> None:
    global _engine, _Session
    url = url or get_settings().database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, **kwargs)
    _Session = sessionmaker(_engine, expire_on_commit=False)
    Base.metadata.create_all(_engine)


def get_db():
    if _Session is None:
        init_db()
    with _Session() as session:
        yield session


def purge_unsaved(db: Session, days: int | None = None) -> int:
    """Data minimization: delete unsaved reports older than the retention window."""
    days = days if days is not None else get_settings().unsaved_report_retention_days
    cutoff = utcnow() - timedelta(days=days)
    res = db.execute(delete(Report).where(Report.saved.is_(False), Report.created_at < cutoff))
    db.commit()
    return res.rowcount or 0
