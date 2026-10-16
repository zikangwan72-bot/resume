from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.approval.models import (
    ApprovalUser,
    ProcessApp,
    ProcessVersion,
)
from app.approval.schemas import (
    ProcessAppUpdate,
)
from app.approval.serializers import (
    serialize_definition_error,
)


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


def _draft_version(db: Session, app: ProcessApp) -> ProcessVersion | None:
    return next(
        (
            version
            for version in _versions_for_app(db, app.id)
            if version.status == "draft"
        ),
        None,
    )


def _current_published_version(db: Session, app: ProcessApp) -> ProcessVersion | None:
    if app.current_version_id is not None:
        current_version = db.get(ProcessVersion, app.current_version_id)
        if current_version is not None and current_version.status == "published":
            return current_version
    return db.scalar(
        select(ProcessVersion)
        .where(
            ProcessVersion.process_app_id == app.id,
            ProcessVersion.status == "published",
        )
        .order_by(desc(ProcessVersion.version_number))
    )


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
