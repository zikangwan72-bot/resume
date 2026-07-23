from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.approval.database import get_approval_db
from app.approval.engine import validate_process_definition
from app.approval.models import (
    ApprovalNode,
    ApprovalRequest,
    ApprovalUser,
    ProcessApp,
    ProcessVersion,
)
from app.approval.schemas import (
    ApprovalUserCreate,
    ApprovalUserUpdate,
    ProcessAppCreate,
    ProcessAppUpdate,
)
from app.approval.serializers import (
    serialize_approval_user,
    serialize_definition_error,
    serialize_process_app,
)
from app.core.security import require_permission
from app.db.models import User

admin_router = APIRouter(prefix="/api/v1/admin", tags=["approval-admin"])


def _get_app(db: Session, app_id: int) -> ProcessApp:
    app = db.get(ProcessApp, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="流程应用不存在")
    return app


def _versions_for_app(db: Session, app_id: int) -> list[ProcessVersion]:
    return db.scalars(
        select(ProcessVersion)
        .where(ProcessVersion.process_app_id == app_id)
        .order_by(desc(ProcessVersion.version_number))
    ).all()


def _editable_version(db: Session, app: ProcessApp) -> ProcessVersion:
    versions = _versions_for_app(db, app.id)
    draft = next((version for version in versions if version.status == "draft"), None)
    if draft is not None:
        return draft
    if app.current_version_id is not None:
        current_version = db.get(ProcessVersion, app.current_version_id)
        if current_version is not None:
            return current_version
    if versions:
        return versions[0]
    raise HTTPException(status_code=500, detail="流程版本数据异常")


def _active_user_ids(db: Session) -> set[str]:
    return set(
        db.scalars(select(ApprovalUser.id).where(ApprovalUser.is_active.is_(True))).all()
    )


def _publish_validation_error(errors: list) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "definition_invalid",
            "errors": [serialize_definition_error(error) for error in errors],
        },
    )


def _flush_or_conflict(db: Session, detail: str) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from exc


def _commit_or_conflict(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from exc


def _unique_copy_code(db: Session, source_code: str) -> str:
    suffix = "-copy"
    candidate = f"{source_code[: 80 - len(suffix)]}{suffix}"
    copy_number = 2
    while db.scalar(select(ProcessApp.id).where(ProcessApp.code == candidate)) is not None:
        suffix = f"-copy-{copy_number}"
        candidate = f"{source_code[: 80 - len(suffix)]}{suffix}"
        copy_number += 1
    return candidate


def _apply_process_update(
    app: ProcessApp, version: ProcessVersion, payload: ProcessAppUpdate
) -> None:
    updates = payload.model_dump(exclude_unset=True)
    for field in ("name", "category", "description"):
        if field in updates:
            setattr(app, field, updates[field])
    if "form_schema" in updates:
        version.form_schema = updates["form_schema"]
    if "flow_schema" in updates:
        version.flow_schema = updates["flow_schema"]
    app.updated_at = datetime.now(UTC)


MonitorStatus = Literal["pending", "approved", "rejected", "revoked"]


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _current_monitor_node(db: Session, request: ApprovalRequest) -> ApprovalNode | None:
    return db.scalar(
        select(ApprovalNode)
        .where(
            ApprovalNode.request_id == request.id,
            ApprovalNode.node_index == request.current_node_index,
            ApprovalNode.status == "pending",
        )
        .order_by(ApprovalNode.id)
    )


def _is_overdue(node: ApprovalNode | None, now: datetime) -> bool:
    if node is None or node.timeout_hours <= 0:
        return False
    created_at = _as_utc(node.created_at)
    return created_at is not None and now - created_at > timedelta(hours=node.timeout_hours)


def _monitor_item(
    db: Session,
    request: ApprovalRequest,
    process_apps: dict[int, ProcessApp],
    versions: dict[int, ProcessVersion],
    users: dict[str, ApprovalUser],
    now: datetime,
) -> dict:
    node = _current_monitor_node(db, request)
    process_app = process_apps.get(request.process_app_id)
    version = versions.get(request.process_version_id)
    applicant = users.get(request.applicant_id)
    applicant_snapshot = request.applicant_snapshot or {}
    flow_node = next(
        (
            item
            for item in request.flow_snapshot
            if item.get("index") == request.current_node_index
            or item.get("id") == (node.node_key if node else None)
        ),
        {},
    )
    approver = users.get(node.approver_id) if node else None
    overdue = _is_overdue(node, now)
    return {
        "id": request.id,
        "title": request.title,
        "status": request.status,
        "submitted_at": request.submitted_at.isoformat() if request.submitted_at else None,
        "created_at": request.created_at.isoformat(),
        "process_app": {
            "id": process_app.id if process_app else request.process_app_id,
            "code": process_app.code if process_app else None,
            "name": process_app.name if process_app else None,
            "version_id": version.id if version else request.process_version_id,
            "version_number": version.version_number if version else None,
        },
        "applicant": {
            "id": request.applicant_id,
            "name": request.applicant_name,
            "email": applicant.email if applicant else None,
            "department": applicant_snapshot.get("department")
            or (applicant.department if applicant else None),
            "position": applicant_snapshot.get("position")
            or (applicant.position if applicant else None),
        },
        "current_node": {
            "id": node.id if node else None,
            "node_index": request.current_node_index,
            "node_key": node.node_key if node else flow_node.get("id"),
            "name": flow_node.get("name") or flow_node.get("label"),
            "status": node.status if node else None,
            "timeout_hours": node.timeout_hours if node else 0,
            "created_at": node.created_at.isoformat() if node else None,
        },
        "current_approver": {
            "id": node.approver_id,
            "name": node.approver_name,
            "email": approver.email if approver else None,
            "department": approver.department if approver else None,
            "position": approver.position if approver else None,
        }
        if node
        else None,
        "overdue": overdue,
    }


def _monitor_context(db: Session, requests: list[ApprovalRequest]) -> tuple[dict, dict, dict]:
    process_ids = {
        request.process_app_id for request in requests if request.process_app_id is not None
    }
    version_ids = {
        request.process_version_id for request in requests if request.process_version_id is not None
    }
    user_ids = {request.applicant_id for request in requests}
    user_ids.update(
        node.approver_id
        for request in requests
        for node in db.scalars(
            select(ApprovalNode).where(ApprovalNode.request_id == request.id)
        ).all()
    )
    return (
        {
            item.id: item
            for item in db.scalars(
                select(ProcessApp).where(ProcessApp.id.in_(process_ids))
            ).all()
        },
        {
            item.id: item
            for item in db.scalars(
                select(ProcessVersion).where(ProcessVersion.id.in_(version_ids))
            ).all()
        },
        {
            item.id: item
            for item in db.scalars(select(ApprovalUser).where(ApprovalUser.id.in_(user_ids))).all()
        },
    )


def _monitor_requests(
    db: Session,
    process_app_id: int | None,
    request_status: MonitorStatus | None,
    submitted_from: datetime | None,
    submitted_to: datetime | None,
    department: str | None,
    applicant: str | None,
    current_approver_id: str | None,
    overdue: bool | None,
) -> list[ApprovalRequest]:
    statement = select(ApprovalRequest).order_by(
        ApprovalRequest.submitted_at.desc(), ApprovalRequest.id.desc()
    )
    if process_app_id is not None:
        statement = statement.where(ApprovalRequest.process_app_id == process_app_id)
    if request_status is not None:
        statement = statement.where(ApprovalRequest.status == request_status)
    if submitted_from is not None:
        statement = statement.where(ApprovalRequest.submitted_at >= submitted_from)
    if submitted_to is not None:
        statement = statement.where(ApprovalRequest.submitted_at <= submitted_to)
    requests = db.scalars(statement).all()
    now = datetime.now(UTC)
    filtered = []
    for request in requests:
        snapshot = request.applicant_snapshot or {}
        node = _current_monitor_node(db, request)
        if department and department not in (snapshot.get("department") or ""):
            continue
        if applicant and applicant not in request.applicant_name:
            continue
        if current_approver_id and (node is None or node.approver_id != current_approver_id):
            continue
        if overdue is not None and _is_overdue(node, now) != overdue:
            continue
        filtered.append(request)
    return filtered


@admin_router.get("/process-monitor/summary")
def process_monitor_summary(
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    requests = db.scalars(select(ApprovalRequest)).all()
    now = datetime.now(UTC)
    overdue = sum(_is_overdue(_current_monitor_node(db, request), now) for request in requests)
    return {
        "data": {
            "total": len(requests),
            "pending": sum(request.status == "pending" for request in requests),
            "approved": sum(request.status == "approved" for request in requests),
            "rejected": sum(request.status == "rejected" for request in requests),
            "revoked": sum(request.status == "revoked" for request in requests),
            "overdue": overdue,
        }
    }


@admin_router.get("/process-monitor/requests")
def process_monitor_requests(
    process_app_id: int | None = Query(default=None, ge=1),
    status: MonitorStatus | None = None,
    submitted_from: datetime | None = None,
    submitted_to: datetime | None = None,
    department: str | None = None,
    applicant: str | None = None,
    current_approver_id: str | None = None,
    overdue: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    requests = _monitor_requests(
        db,
        process_app_id,
        status,
        submitted_from,
        submitted_to,
        department,
        applicant,
        current_approver_id,
        overdue,
    )
    start = (page - 1) * page_size
    selected = requests[start : start + page_size]
    process_apps, versions, users = _monitor_context(db, selected)
    now = datetime.now(UTC)
    return {
        "data": {
            "items": [
                _monitor_item(db, request, process_apps, versions, users, now)
                for request in selected
            ],
            "total": len(requests),
            "page": page,
            "page_size": page_size,
        }
    }


@admin_router.get("/process-apps")
def list_process_apps(
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    apps = db.scalars(select(ProcessApp).order_by(desc(ProcessApp.updated_at))).all()
    return {"data": [serialize_process_app(app, _editable_version(db, app)) for app in apps]}


@admin_router.post("/process-apps", status_code=status.HTTP_201_CREATED)
def create_process_app(
    body: ProcessAppCreate,
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    if db.scalar(select(ProcessApp.id).where(ProcessApp.code == body.code)) is not None:
        raise HTTPException(status_code=409, detail="流程编号已存在")
    app = ProcessApp(
        code=body.code,
        name=body.name,
        category=body.category,
        description=body.description,
        status="draft",
    )
    db.add(app)
    _flush_or_conflict(db, "流程编号已存在")
    version = ProcessVersion(
        process_app_id=app.id,
        version_number=1,
        status="draft",
        form_schema=body.form_schema,
        flow_schema=body.flow_schema,
    )
    db.add(version)
    _flush_or_conflict(db, "流程版本冲突，请刷新后重试")
    app.current_version_id = version.id
    _commit_or_conflict(db, "流程编号已存在")
    db.refresh(app)
    db.refresh(version)
    return {"data": serialize_process_app(app, version)}


@admin_router.get("/process-apps/{app_id}")
def get_process_app(
    app_id: int,
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    app = _get_app(db, app_id)
    return {"data": serialize_process_app(app, _editable_version(db, app))}


@admin_router.put("/process-apps/{app_id}")
def update_process_app(
    app_id: int,
    body: ProcessAppUpdate,
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    app = _get_app(db, app_id)
    if body.code is not None and body.code != app.code:
        if app.status == "published":
            raise HTTPException(status_code=400, detail="已发布流程的编号不可修改")
        if db.scalar(select(ProcessApp.id).where(ProcessApp.code == body.code)) is not None:
            raise HTTPException(status_code=409, detail="流程编号已存在")
        app.code = body.code

    editable_version = _editable_version(db, app)
    if editable_version.status == "published":
        editable_version = ProcessVersion(
            process_app_id=app.id,
            version_number=_versions_for_app(db, app.id)[0].version_number + 1,
            status="draft",
            form_schema=deepcopy(editable_version.form_schema),
            flow_schema=deepcopy(editable_version.flow_schema),
        )
        db.add(editable_version)
        _flush_or_conflict(db, "流程版本冲突，请刷新后重试")

    _apply_process_update(app, editable_version, body)
    _commit_or_conflict(db, "流程版本冲突，请刷新后重试")
    db.refresh(app)
    db.refresh(editable_version)
    return {"data": serialize_process_app(app, editable_version)}


@admin_router.post("/process-apps/{app_id}/publish")
def publish_process_app(
    app_id: int,
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    app = _get_app(db, app_id)
    version = _editable_version(db, app)
    errors = validate_process_definition(
        version.form_schema,
        version.flow_schema,
        _active_user_ids(db),
    )
    if errors:
        raise _publish_validation_error(errors)
    version.status = "published"
    version.published_at = datetime.now(UTC)
    app.status = "published"
    app.current_version_id = version.id
    app.updated_at = datetime.now(UTC)
    _commit_or_conflict(db, "流程版本冲突，请刷新后重试")
    db.refresh(app)
    db.refresh(version)
    return {"data": serialize_process_app(app, version)}


@admin_router.post("/process-apps/{app_id}/copy", status_code=status.HTTP_201_CREATED)
def copy_process_app(
    app_id: int,
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    source = _get_app(db, app_id)
    source_version = _editable_version(db, source)
    app = ProcessApp(
        code=_unique_copy_code(db, source.code),
        name=f"{source.name}（副本）",
        category=source.category,
        description=source.description,
        status="draft",
    )
    db.add(app)
    _flush_or_conflict(db, "流程编号已存在")
    version = ProcessVersion(
        process_app_id=app.id,
        version_number=1,
        status="draft",
        form_schema=deepcopy(source_version.form_schema),
        flow_schema=deepcopy(source_version.flow_schema),
    )
    db.add(version)
    _flush_or_conflict(db, "流程版本冲突，请刷新后重试")
    app.current_version_id = version.id
    _commit_or_conflict(db, "流程编号已存在")
    db.refresh(app)
    db.refresh(version)
    return {"data": serialize_process_app(app, version)}


@admin_router.post("/process-apps/{app_id}/deactivate")
def deactivate_process_app(
    app_id: int,
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    app = _get_app(db, app_id)
    app.status = "inactive"
    app.updated_at = datetime.now(UTC)
    version = _editable_version(db, app)
    _commit_or_conflict(db, "流程版本冲突，请刷新后重试")
    db.refresh(app)
    return {"data": serialize_process_app(app, version)}


@admin_router.get("/users")
def list_users(
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    users = db.scalars(select(ApprovalUser).order_by(ApprovalUser.display_name)).all()
    return {"data": [serialize_approval_user(user) for user in users]}


@admin_router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    body: ApprovalUserCreate,
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    if db.scalar(select(ApprovalUser.id).where(ApprovalUser.email == body.email)) is not None:
        raise HTTPException(status_code=409, detail="邮箱已存在")
    user = ApprovalUser(id=str(uuid4()), **body.model_dump())
    db.add(user)
    _commit_or_conflict(db, "邮箱已存在")
    db.refresh(user)
    return {"data": serialize_approval_user(user)}


@admin_router.put("/users/{user_id}")
def update_user(
    user_id: str,
    body: ApprovalUserUpdate,
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    user = db.get(ApprovalUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    updates = body.model_dump(exclude_unset=True)
    email = updates.get("email")
    if email is not None:
        existing_user_id = db.scalar(select(ApprovalUser.id).where(ApprovalUser.email == email))
        if existing_user_id is not None and existing_user_id != user.id:
            raise HTTPException(status_code=409, detail="邮箱已存在")
    for field, value in updates.items():
        setattr(user, field, value)
    _commit_or_conflict(db, "邮箱已存在")
    db.refresh(user)
    return {"data": serialize_approval_user(user)}
