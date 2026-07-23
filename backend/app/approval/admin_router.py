from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.approval.database import get_approval_db
from app.approval.engine import validate_process_definition
from app.approval.models import ApprovalUser, ProcessApp, ProcessVersion
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
    db.flush()
    version = ProcessVersion(
        process_app_id=app.id,
        version_number=1,
        status="draft",
        form_schema=body.form_schema,
        flow_schema=body.flow_schema,
    )
    db.add(version)
    db.flush()
    app.current_version_id = version.id
    db.commit()
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
    if app.status == "published" and editable_version.status != "draft":
        editable_version = ProcessVersion(
            process_app_id=app.id,
            version_number=editable_version.version_number + 1,
            status="draft",
            form_schema=deepcopy(editable_version.form_schema),
            flow_schema=deepcopy(editable_version.flow_schema),
        )
        db.add(editable_version)
        db.flush()

    _apply_process_update(app, editable_version, body)
    db.commit()
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
    db.commit()
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
    db.flush()
    version = ProcessVersion(
        process_app_id=app.id,
        version_number=1,
        status="draft",
        form_schema=deepcopy(source_version.form_schema),
        flow_schema=deepcopy(source_version.flow_schema),
    )
    db.add(version)
    db.flush()
    app.current_version_id = version.id
    db.commit()
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
    db.commit()
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
    db.commit()
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
    db.commit()
    db.refresh(user)
    return {"data": serialize_approval_user(user)}
