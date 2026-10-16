import hmac
from datetime import UTC, datetime
from secrets import token_urlsafe
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.approval.database import get_approval_db
from app.approval.models import ApprovalUser
from app.approval.serializers import serialize_approval_user
from app.business.asset_service import (
    active_record_payload,
    apply_inventory_record_update,
    asset_payload,
    asset_qr_token,
    exception_payload,
    inventory_scope_condition,
    parse_asset_rows,
    persist_photo_url,
    qr_payload,
    record_payload,
    row_to_import,
    task_payload,
)
from app.business.models import Asset, AssetException, InventoryRecord, InventoryTask
from app.business.schemas import (
    AssetCreate,
    AssetImportCommit,
    AssetUpdate,
    InventoryRecordUpdate,
    InventoryTaskCreate,
    InventoryTaskUpdate,
    MobileInventorySubmit,
    ResolveExceptionRequest,
)
from app.core.pagination import PageParams, page_params, page_response, paginate_select
from app.core.security import require_permission
from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/summary")
def asset_summary(_: User = Depends(require_permission("asset:view")), db: Session = Depends(get_db)) -> dict:
    total, total_value, exception_count, inventory_total, inventory_checked = db.execute(
        select(
            select(func.count(Asset.id)).scalar_subquery(),
            select(func.coalesce(func.sum(Asset.value), 0)).scalar_subquery(),
            select(func.count(AssetException.id))
            .where(AssetException.status != "已归档")
            .scalar_subquery(),
            select(func.coalesce(func.sum(InventoryTask.total_count), 0)).scalar_subquery(),
            select(func.coalesce(func.sum(InventoryTask.checked_count), 0)).scalar_subquery(),
        )
    ).one()
    completion = (
        min(100, round((inventory_checked / inventory_total) * 100))
        if inventory_total
        else 0
    )
    return {"data": {"asset_count": total, "total_value": total_value, "exception_count": exception_count, "inventory_completion": completion}}


@router.get("/overview")
def asset_overview(
    _: User = Depends(require_permission("asset:view")),
    db: Session = Depends(get_db),
    approval_db: Session = Depends(get_approval_db),
) -> dict:
    summary = asset_summary(_, db)["data"]
    assets = db.scalars(select(Asset).order_by(Asset.created_at.desc())).all()
    tasks = db.scalars(
        select(InventoryTask).order_by(InventoryTask.created_at.desc())
    ).all()
    exception_rows = db.execute(
        select(AssetException, Asset)
        .join(Asset, Asset.id == AssetException.asset_id)
        .order_by(AssetException.created_at.desc())
    ).all()
    users = approval_db.scalars(
        select(ApprovalUser).order_by(ApprovalUser.display_name)
    ).all()
    return {
        "data": {
            "summary": summary,
            "assets": [asset_payload(row) for row in assets],
            "tasks": [task_payload(row) for row in tasks],
            "exceptions": [
                exception_payload(exception, db, asset) for exception, asset in exception_rows
            ],
            "inventory_owners": [serialize_approval_user(user) for user in users],
        }
    }


@router.get("")
def list_assets(keyword: str = "", status_filter: str = Query("", alias="status"), category: str = "", department: str = "", paging: PageParams | None = Depends(page_params), _: User = Depends(require_permission("asset:view")), db: Session = Depends(get_db)) -> dict:
    query = select(Asset).order_by(Asset.created_at.desc())
    if keyword:
        term = f"%{keyword}%"
        query = query.where(or_(Asset.asset_code.like(term), Asset.name.like(term), Asset.department.like(term), Asset.owner.like(term)))
    if status_filter: query = query.where(Asset.status == status_filter)
    if category: query = query.where(Asset.category == category)
    if department: query = query.where(Asset.department == department)
    rows, meta = paginate_select(db, query.order_by(Asset.id.desc()), paging)
    return page_response([asset_payload(row) for row in rows], meta)


@router.post("/import/preview")
def preview_asset_import(file: UploadFile = File(...), _: User = Depends(require_permission("asset:manage")), db: Session = Depends(get_db)) -> dict:
    rows = parse_asset_rows(file)
    existing_codes = set(db.scalars(select(Asset.asset_code)).all())
    seen_codes: set[str] = set()
    parsed = [row_to_import(row, index + 2, existing_codes, seen_codes) for index, row in enumerate(rows)]
    return {
        "data": {
            "total": len(parsed),
            "valid_count": sum(1 for row in parsed if row["valid"]),
            "error_count": sum(1 for row in parsed if not row["valid"]),
            "rows": parsed,
        }
    }


@router.post("/import/commit", status_code=status.HTTP_201_CREATED)
def commit_asset_import(payload: AssetImportCommit, _: User = Depends(require_permission("asset:manage")), db: Session = Depends(get_db)) -> dict:
    existing_codes = set(db.scalars(select(Asset.asset_code)).all())
    created: list[Asset] = []
    skipped: list[dict] = []
    for row in payload.rows:
        if row.asset_code in existing_codes:
            skipped.append({"asset_code": row.asset_code, "reason": "资产编号已存在"})
            continue
        asset = Asset(**row.model_dump(exclude={"row_number"}), asset_uuid=str(uuid4()), qr_secret=token_urlsafe(24))
        db.add(asset)
        created.append(asset)
        existing_codes.add(row.asset_code)
    db.commit()
    return {"data": {"created_count": len(created), "skipped": skipped}}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_asset(payload: AssetCreate, _: User = Depends(require_permission("asset:manage")), db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(Asset).where(Asset.asset_code == payload.asset_code)):
        raise HTTPException(status_code=409, detail="资产编号已存在")
    row = Asset(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"data": asset_payload(row)}


@router.patch("/{asset_id}")
def update_asset(asset_id: int, payload: AssetUpdate, _: User = Depends(require_permission("asset:manage")), db: Session = Depends(get_db)) -> dict:
    row = db.get(Asset, asset_id)
    if row is None: raise HTTPException(status_code=404, detail="资产不存在")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    row.updated_at = datetime.now(UTC); db.commit(); db.refresh(row)
    return {"data": asset_payload(row)}


@router.delete("/{asset_id}")
def delete_asset(asset_id: int, _: User = Depends(require_permission("asset:manage")), db: Session = Depends(get_db)) -> dict:
    row = db.get(Asset, asset_id)
    if row is None: raise HTTPException(status_code=404, detail="资产不存在")
    db.delete(row); db.commit(); return {"data": {"id": asset_id, "deleted": True}}


@router.get("/{asset_id}/qr")
def get_asset_qr(asset_id: int, request: Request, _: User = Depends(require_permission("asset:manage")), db: Session = Depends(get_db)) -> dict:
    row = db.get(Asset, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="资产不存在")
    return {"data": qr_payload(row, request)}


@router.post("/{asset_id}/qr/rotate")
def rotate_asset_qr(asset_id: int, request: Request, _: User = Depends(require_permission("asset:manage")), db: Session = Depends(get_db)) -> dict:
    row = db.get(Asset, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="资产不存在")
    row.qr_secret = token_urlsafe(24)
    db.commit()
    db.refresh(row)
    return {"data": qr_payload(row, request)}


@router.get("/mobile-inventory/asset")
def mobile_inventory_asset(asset_uuid: str, token: str, _: User = Depends(require_permission("inventory:self_check")), db: Session = Depends(get_db)) -> dict:
    asset = db.scalar(select(Asset).where(Asset.asset_uuid == asset_uuid))
    if asset is None or not hmac.compare_digest(asset_qr_token(asset), token):
        raise HTTPException(status_code=404, detail="资产二维码无效或已更新")
    active_record = active_record_payload(asset, db)
    return {
        "data": {
            "asset": asset_payload(asset),
            "active_record": active_record,
            "locked": bool(active_record and active_record["locked"]),
            "message": "暂无进行中的盘点任务" if active_record is None else "",
        }
    }


@router.post("/mobile-inventory/scan")
def submit_mobile_inventory(payload: MobileInventorySubmit, user: User = Depends(require_permission("inventory:self_check")), db: Session = Depends(get_db)) -> dict:
    asset = db.scalar(select(Asset).where(Asset.asset_uuid == payload.asset_uuid))
    if asset is None or not hmac.compare_digest(asset_qr_token(asset), payload.token):
        raise HTTPException(status_code=404, detail="资产二维码无效或已更新")
    task = db.get(InventoryTask, payload.task_id) if payload.task_id else None
    record = None
    if task:
        if task.status != "进行中":
            raise HTTPException(status_code=409, detail="本次盘点任务已结束，不能重复提交")
        record = db.scalar(select(InventoryRecord).where(InventoryRecord.task_id == task.id, InventoryRecord.asset_id == asset.id))
    if record is None:
        record = db.scalar(
            select(InventoryRecord)
            .join(InventoryTask, InventoryRecord.task_id == InventoryTask.id)
            .where(InventoryRecord.asset_id == asset.id, InventoryTask.status == "进行中")
            .order_by(InventoryRecord.id.desc())
        )
        task = db.get(InventoryTask, record.task_id) if record else task
    if record is None:
        raise HTTPException(status_code=409, detail="暂无进行中的盘点任务")
    if record.result != "未盘点":
        raise HTTPException(status_code=409, detail="本次盘点任务已完成，不能重复提交")
    remark_parts = []
    if payload.current_owner:
        remark_parts.append(f"现场使用人：{payload.current_owner}")
    if payload.remark:
        remark_parts.append(payload.remark)
    apply_inventory_record_update(
        record,
        asset,
        task,
        result=payload.result,
        actual_location=payload.actual_location,
        remark="\n".join(remark_parts) or None,
        photo_url=persist_photo_url(payload.photo_url, asset, record.id),
        checked_by=user.display_name,
        db=db,
    )
    db.commit()
    db.refresh(record)
    return {"data": record_payload(record, db)}


@router.get("/inventory-tasks")
def list_inventory_tasks(_: User = Depends(require_permission("asset:view")), db: Session = Depends(get_db)) -> dict:
    return {"data": [task_payload(row) for row in db.scalars(select(InventoryTask).order_by(InventoryTask.created_at.desc())).all()]}


@router.post("/inventory-tasks", status_code=status.HTTP_201_CREATED)
def create_inventory_task(payload: InventoryTaskCreate, _: User = Depends(require_permission("inventory:manage")), db: Session = Depends(get_db)) -> dict:
    count_query = select(func.count(Asset.id))
    scope_condition = inventory_scope_condition(payload.scope)
    if scope_condition is not None:
        count_query = count_query.where(scope_condition)
    total = db.scalar(count_query) or 0
    row = InventoryTask(**payload.model_dump(), total_count=total)
    db.add(row); db.commit(); db.refresh(row)
    return {"data": task_payload(row)}


@router.patch("/inventory-tasks/{task_id}")
def update_inventory_task(task_id: int, payload: InventoryTaskUpdate, _: User = Depends(require_permission("inventory:manage")), db: Session = Depends(get_db)) -> dict:
    row = db.get(InventoryTask, task_id)
    if row is None: raise HTTPException(status_code=404, detail="盘点任务不存在")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    row.updated_at = datetime.now(UTC); db.commit(); db.refresh(row)
    return {"data": task_payload(row)}


@router.post("/inventory-tasks/{task_id}/start")
def start_inventory_task(task_id: int, _: User = Depends(require_permission("inventory:manage")), db: Session = Depends(get_db)) -> dict:
    task = db.get(InventoryTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="盘点任务不存在")
    if task.status in {"已结束", "已完成"}:
        raise HTTPException(status_code=409, detail="该盘点任务已结束，只能查看历史记录")
    for other in db.scalars(
        select(InventoryTask).where(InventoryTask.status == "进行中", InventoryTask.id != task.id)
    ).all():
        other.status = "已结束"
        other.updated_at = datetime.now(UTC)
    existing = db.scalar(select(func.count(InventoryRecord.id)).where(InventoryRecord.task_id == task_id)) or 0
    if not existing:
        asset_query = select(Asset).order_by(Asset.asset_code)
        scope_condition = inventory_scope_condition(task.scope)
        if scope_condition is not None:
            asset_query = asset_query.where(scope_condition)
        assets = db.scalars(asset_query).all()
        db.add_all([InventoryRecord(task_id=task_id, asset_id=asset.id) for asset in assets])
        task.total_count = len(assets)
    task.status = "进行中" if task.total_count else "已完成"
    task.updated_at = datetime.now(UTC)
    db.commit(); db.refresh(task)
    return {"data": task_payload(task)}


@router.get("/inventory-tasks/{task_id}/records")
def list_inventory_records(task_id: int, _: User = Depends(require_permission("asset:view")), db: Session = Depends(get_db)) -> dict:
    if db.get(InventoryTask, task_id) is None:
        raise HTTPException(status_code=404, detail="盘点任务不存在")
    rows = db.execute(
        select(InventoryRecord, Asset)
        .join(Asset, Asset.id == InventoryRecord.asset_id)
        .where(InventoryRecord.task_id == task_id)
        .order_by(InventoryRecord.id)
    ).all()
    return {"data": [record_payload(row, db, asset) for row, asset in rows]}


@router.patch("/inventory-records/{record_id}")
def update_inventory_record(record_id: int, payload: InventoryRecordUpdate, user: User = Depends(require_permission("inventory:manage")), db: Session = Depends(get_db)) -> dict:
    row = db.get(InventoryRecord, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="盘点记录不存在")
    task = db.get(InventoryTask, row.task_id)
    asset = db.get(Asset, row.asset_id)
    apply_inventory_record_update(
        row,
        asset,
        task,
        result=payload.result,
        actual_location=payload.actual_location,
        remark=payload.remark,
        photo_url=persist_photo_url(payload.photo_url, asset, row.id),
        checked_by=user.display_name,
        db=db,
    )
    db.commit(); db.refresh(row)
    return {"data": record_payload(row, db)}


@router.get("/exceptions")
def list_exceptions(_: User = Depends(require_permission("asset:view")), db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(AssetException, Asset)
        .join(Asset, Asset.id == AssetException.asset_id)
        .order_by(AssetException.created_at.desc())
    ).all()
    return {"data": [exception_payload(row, db, asset) for row, asset in rows]}


@router.post("/exceptions/{exception_id}/resolve")
def resolve_exception(exception_id: int, payload: ResolveExceptionRequest, user: User = Depends(require_permission("inventory:manage")), db: Session = Depends(get_db)) -> dict:
    row = db.get(AssetException, exception_id)
    if row is None: raise HTTPException(status_code=404, detail="资产异常不存在")
    row.status = "已归档"; row.resolution = payload.resolution; row.resolved_by = user.display_name; row.resolved_at = datetime.now(UTC)
    db.commit(); db.refresh(row)
    return {"data": exception_payload(row, db)}
