from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.approval.codegen import generate_process_code
from app.approval.database import get_approval_db
from app.approval.engine import validate_process_definition
from app.approval.models import (
    ApprovalRequest,
    ApprovalUser,
    ProcessApp,
    ProcessVersion,
)
from app.approval.process_admin_service import (
    _active_user_ids,
    _apply_process_update,
    _commit_or_conflict,
    _editable_version,
    _flush_or_conflict,
    _get_app,
    _publish_validation_error,
    _unique_copy_code,
    _versions_for_app,
)
from app.approval.process_monitor import (
    MonitorStatus,
    _monitor_context,
    _monitor_item,
    _monitor_requests,
    _overdue_node_exists,
)
from app.approval.schemas import (
    ApprovalUserCreate,
    ApprovalUserUpdate,
    ProcessAppCreate,
    ProcessAppUpdate,
)
from app.approval.serializers import (
    serialize_approval_user,
    serialize_process_app,
    serialize_process_app_list,
)
from app.core.security import require_permission
from app.db.models import User

admin_router = APIRouter(prefix="/api/v1/admin", tags=["approval-admin"])


@admin_router.get("/process-monitor/summary")
def process_monitor_summary(
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    overdue_node = _overdue_node_exists(db)
    counts = db.execute(
        select(
            func.count(ApprovalRequest.id),
            func.sum(case((ApprovalRequest.status == "pending", 1), else_=0)),
            func.sum(case((ApprovalRequest.status == "approved", 1), else_=0)),
            func.sum(case((ApprovalRequest.status == "rejected", 1), else_=0)),
            func.sum(case((ApprovalRequest.status == "revoked", 1), else_=0)),
            func.sum(case((overdue_node, 1), else_=0)),
        )
    ).one()
    return {
        "data": {
            "total": counts[0],
            "pending": counts[1] or 0,
            "approved": counts[2] or 0,
            "rejected": counts[3] or 0,
            "revoked": counts[4] or 0,
            "overdue": counts[5] or 0,
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
    statement_requests, total = _monitor_requests(
        db,
        process_app_id,
        status,
        submitted_from,
        submitted_to,
        department,
        applicant,
        current_approver_id,
        overdue,
        (page - 1) * page_size,
        page_size,
    )
    selected = statement_requests
    process_apps, versions, users, current_nodes = _monitor_context(db, selected)
    now = datetime.now(UTC)
    return {
        "data": {
            "items": [
                _monitor_item(
                    request,
                    process_apps,
                    versions,
                    users,
                    current_nodes[request.id],
                    now,
                )
                for request in selected
            ],
            "total": total,
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
    app_ids = [app.id for app in apps]
    versions_by_app: dict[int, list[ProcessVersion]] = {app_id: [] for app_id in app_ids}
    if app_ids:
        versions = db.scalars(
            select(ProcessVersion)
            .where(ProcessVersion.process_app_id.in_(app_ids))
            .order_by(ProcessVersion.process_app_id, desc(ProcessVersion.version_number))
        ).all()
        for version in versions:
            versions_by_app[version.process_app_id].append(version)

    def version_pair(app: ProcessApp) -> tuple[ProcessVersion | None, ProcessVersion | None]:
        versions = versions_by_app[app.id]
        current = next(
            (
                version
                for version in versions
                if version.id == app.current_version_id and version.status == "published"
            ),
            None,
        ) or next((version for version in versions if version.status == "published"), None)
        draft = next((version for version in versions if version.status == "draft"), None)
        return current, draft

    return {
        "data": [
            serialize_process_app_list(app, *version_pair(app))
            for app in apps
        ]
    }


@admin_router.post("/process-apps", status_code=status.HTTP_201_CREATED)
def create_process_app(
    body: ProcessAppCreate,
    _: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict:
    app = ProcessApp(
        code=generate_process_code(db, body.category),
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
        raise HTTPException(status_code=400, detail="已生成的流程编号不可修改")

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
