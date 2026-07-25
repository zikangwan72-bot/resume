from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AssetCreate(BaseModel):
    asset_code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=80)
    department: str = Field(min_length=1, max_length=120)
    owner: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=120)
    status: str = "在用"
    purchase_date: date | None = None
    value: float = Field(default=0, ge=0)


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    department: str | None = Field(default=None, min_length=1, max_length=120)
    owner: str | None = Field(default=None, min_length=1, max_length=100)
    location: str | None = Field(default=None, min_length=1, max_length=120)
    status: str | None = None
    purchase_date: date | None = None
    value: float | None = Field(default=None, ge=0)


class InventoryTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    scope: str = Field(min_length=1, max_length=200)
    owner: str = Field(min_length=1, max_length=100)
    due_date: date | None = None
    status: str = "草稿"


class InventoryTaskUpdate(BaseModel):
    status: str | None = None
    checked_count: int | None = Field(default=None, ge=0)
    exception_count: int | None = Field(default=None, ge=0)


class ResolveExceptionRequest(BaseModel):
    resolution: str = Field(min_length=1, max_length=2000)


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    department: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=120)
    employment_type: str = "实习"
    description: str = Field(min_length=1)
    requirements: str = Field(min_length=1)
    status: str = "开放"


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    department: str | None = Field(default=None, min_length=1, max_length=120)
    location: str | None = Field(default=None, min_length=1, max_length=120)
    employment_type: str | None = None
    description: str | None = Field(default=None, min_length=1)
    requirements: str | None = Field(default=None, min_length=1)
    status: str | None = None


class ApplicationCreate(BaseModel):
    job_id: int
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    school: str | None = Field(default=None, max_length=160)
    major: str | None = Field(default=None, max_length=120)
    graduation_year: int | None = Field(default=None, ge=2000, le=2100)
    resume_text: str = ""
    cover_note: str | None = None


class ApplicationStatusUpdate(BaseModel):
    status: str
    review_note: str | None = None


class BusinessModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
