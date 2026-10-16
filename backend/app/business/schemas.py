from datetime import date, datetime
from typing import Literal

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


class AssetImportRow(AssetCreate):
    row_number: int | None = None


class AssetImportCommit(BaseModel):
    rows: list[AssetImportRow] = Field(min_length=1)


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
    due_date: date
    status: str = "草稿"


class InventoryTaskUpdate(BaseModel):
    status: str | None = None
    checked_count: int | None = Field(default=None, ge=0)
    exception_count: int | None = Field(default=None, ge=0)


class InventoryRecordUpdate(BaseModel):
    result: Literal["正常", "位置不符", "盘亏", "损坏"]
    actual_location: str | None = Field(default=None, max_length=120)
    remark: str | None = Field(default=None, max_length=1000)
    photo_url: str | None = None


class MobileInventorySubmit(BaseModel):
    asset_uuid: str
    token: str
    task_id: int | None = None
    result: Literal["正常", "位置不符", "盘亏", "损坏"] = "正常"
    actual_location: str = Field(min_length=1, max_length=120)
    current_owner: str | None = Field(default=None, max_length=100)
    remark: str | None = Field(default=None, max_length=1000)
    photo_url: str = Field(min_length=1)


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


TicketCategory = Literal["账号权限", "硬件设备", "软件安装", "网络连接", "其他"]
TicketPriority = Literal["低", "中", "高", "紧急"]


class TicketCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=5, max_length=4000)
    category: TicketCategory
    priority: TicketPriority = "中"
    contact: str | None = Field(default=None, max_length=120)


class TicketAssign(BaseModel):
    assignee_id: str | None = None


class TicketResolve(BaseModel):
    resolution: str = Field(min_length=2, max_length=4000)


class TicketClose(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class TicketReason(BaseModel):
    reason: str = Field(min_length=2, max_length=1000)


class TicketComment(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
