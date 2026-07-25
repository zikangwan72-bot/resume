from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.business.models import Asset, AssetException, InventoryTask
from app.business.schemas import AssetCreate, AssetUpdate, InventoryTaskCreate, InventoryTaskUpdate, ResolveExceptionRequest
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/assets", tags=["assets"])


def asset_payload(row: Asset) -> dict:
    return {"id": row.id, "asset_code": row.asset_code, "name": row.name, "category": row.category, "department": row.department, "owner": row.owner, "location": row.location, "status": row.status, "purchase_date": row.purchase_date, "value": row.value, "last_inventory_at": row.last_inventory_at, "created_at": row.created_at, "updated_at": row.updated_at}


def task_payload(row: InventoryTask) -> dict:
    return {"id": row.id, "name": row.name, "scope": row.scope, "owner": row.owner, "status": row.status, "due_date": row.due_date, "total_count": row.total_count, "checked_count": row.checked_count, "exception_count": row.exception_count, "created_at": row.created_at, "updated_at": row.updated_at}


def exception_payload(row: AssetException, db: Session) -> dict:
    asset = db.get(Asset, row.asset_id)
    return {"id": row.id, "asset_id": row.asset_id, "asset_code": asset.asset_code if asset else "", "asset_name": asset.name if asset else "", "department": asset.department if asset else "", "type": row.type, "description": row.description, "status": row.status, "resolution": row.resolution, "resolved_by": row.resolved_by, "resolved_at": row.resolved_at, "created_at": row.created_at}


@router.get("/summary")
def asset_summary(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count(Asset.id))) or 0
    total_value = db.scalar(select(func.coalesce(func.sum(Asset.value), 0))) or 0
    exception_count = db.scalar(select(func.count(AssetException.id)).where(AssetException.status != "已归档")) or 0
    inventory_total = db.scalar(select(func.sum(InventoryTask.total_count))) or 0
    inventory_checked = db.scalar(select(func.sum(InventoryTask.checked_count))) or 0
    completion = round((inventory_checked / inventory_total) * 100) if inventory_total else 0
    return {"data": {"asset_count": total, "total_value": total_value, "exception_count": exception_count, "inventory_completion": completion}}


@router.get("")
def list_assets(keyword: str = "", status_filter: str = Query("", alias="status"), category: str = "", department: str = "", _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    query = select(Asset).order_by(Asset.created_at.desc())
    if keyword:
        term = f"%{keyword}%"
        query = query.where(or_(Asset.asset_code.like(term), Asset.name.like(term), Asset.department.like(term), Asset.owner.like(term)))
    if status_filter: query = query.where(Asset.status == status_filter)
    if category: query = query.where(Asset.category == category)
    if department: query = query.where(Asset.department == department)
    return {"data": [asset_payload(row) for row in db.scalars(query).all()]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_asset(payload: AssetCreate, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(Asset).where(Asset.asset_code == payload.asset_code)):
        raise HTTPException(status_code=409, detail="资产编号已存在")
    row = Asset(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"data": asset_payload(row)}


@router.patch("/{asset_id}")
def update_asset(asset_id: int, payload: AssetUpdate, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(Asset, asset_id)
    if row is None: raise HTTPException(status_code=404, detail="资产不存在")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    row.updated_at = datetime.now(UTC); db.commit(); db.refresh(row)
    return {"data": asset_payload(row)}


@router.delete("/{asset_id}")
def delete_asset(asset_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(Asset, asset_id)
    if row is None: raise HTTPException(status_code=404, detail="资产不存在")
    db.delete(row); db.commit(); return {"data": {"id": asset_id, "deleted": True}}


@router.get("/inventory-tasks")
def list_inventory_tasks(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {"data": [task_payload(row) for row in db.scalars(select(InventoryTask).order_by(InventoryTask.created_at.desc())).all()]}


@router.post("/inventory-tasks", status_code=status.HTTP_201_CREATED)
def create_inventory_task(payload: InventoryTaskCreate, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count(Asset.id))) or 0
    row = InventoryTask(**payload.model_dump(), total_count=total)
    db.add(row); db.commit(); db.refresh(row)
    return {"data": task_payload(row)}


@router.patch("/inventory-tasks/{task_id}")
def update_inventory_task(task_id: int, payload: InventoryTaskUpdate, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(InventoryTask, task_id)
    if row is None: raise HTTPException(status_code=404, detail="盘点任务不存在")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    row.updated_at = datetime.now(UTC); db.commit(); db.refresh(row)
    return {"data": task_payload(row)}


@router.get("/exceptions")
def list_exceptions(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(AssetException).order_by(AssetException.created_at.desc())).all()
    return {"data": [exception_payload(row, db) for row in rows]}


@router.post("/exceptions/{exception_id}/resolve")
def resolve_exception(exception_id: int, payload: ResolveExceptionRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(AssetException, exception_id)
    if row is None: raise HTTPException(status_code=404, detail="资产异常不存在")
    row.status = "已归档"; row.resolution = payload.resolution; row.resolved_by = user.display_name; row.resolved_at = datetime.now(UTC)
    db.commit(); db.refresh(row)
    return {"data": exception_payload(row, db)}
