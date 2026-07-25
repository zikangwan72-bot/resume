from datetime import UTC, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(80), index=True)
    department: Mapped[str] = mapped_column(String(120), index=True)
    owner: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="在用", index=True)
    purchase_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    value: Mapped[float] = mapped_column(Float, default=0)
    last_inventory_at: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class InventoryTask(Base):
    __tablename__ = "inventory_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160))
    scope: Mapped[str] = mapped_column(String(200))
    owner: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="草稿", index=True)
    due_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    checked_count: Mapped[int] = mapped_column(Integer, default=0)
    exception_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class InventoryRecord(Base):
    __tablename__ = "inventory_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("inventory_tasks.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    result: Mapped[str] = mapped_column(String(30), default="未盘点")
    actual_location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssetException(Base):
    __tablename__ = "asset_exceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    inventory_record_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_records.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="待核实", index=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class JobOpening(Base):
    __tablename__ = "job_openings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(160))
    department: Mapped[str] = mapped_column(String(120))
    location: Mapped[str] = mapped_column(String(120))
    employment_type: Mapped[str] = mapped_column(String(50), default="实习")
    description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="开放", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class CandidateApplication(Base):
    __tablename__ = "candidate_applications"
    __table_args__ = (UniqueConstraint("job_id", "email", name="uq_application_job_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_openings.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    school: Mapped[str | None] = mapped_column(String(160), nullable=True)
    major: Mapped[str | None] = mapped_column(String(120), nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resume_text: Mapped[str] = mapped_column(Text, default="")
    cover_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="待初筛", index=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
