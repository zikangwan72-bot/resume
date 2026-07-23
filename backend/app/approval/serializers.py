from typing import Any

from app.approval.models import ApprovalUser, ProcessApp, ProcessVersion
from app.approval.schemas import DefinitionError


def serialize_definition_error(error: DefinitionError) -> dict[str, str | None]:
    return {"code": error.code, "message": error.message, "target_id": error.target_id}


def serialize_approval_user(user: ApprovalUser) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "department": user.department,
        "position": user.position,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
    }


def serialize_process_app(app: ProcessApp, version: ProcessVersion) -> dict[str, Any]:
    fields = version.form_schema.get("fields", [])
    nodes = version.flow_schema.get("nodes", [])
    return {
        "id": app.id,
        "code": app.code,
        "name": app.name,
        "category": app.category,
        "description": app.description,
        "status": app.status,
        "version_id": version.id,
        "version_number": version.version_number,
        "version_status": version.status,
        "current_version_id": app.current_version_id,
        "field_count": len(fields) if isinstance(fields, list) else 0,
        "approval_node_count": sum(
            1
            for node in nodes
            if isinstance(node, dict) and node.get("type") in {"approval", "countersign"}
        ),
        "form_schema": version.form_schema,
        "flow_schema": version.flow_schema,
        "published_at": version.published_at.isoformat() if version.published_at else None,
        "created_at": app.created_at.isoformat(),
        "updated_at": app.updated_at.isoformat(),
    }


def serialize_process_app_list(
    app: ProcessApp,
    current_version: ProcessVersion | None,
    draft_version: ProcessVersion | None,
) -> dict[str, Any]:
    version = current_version or draft_version
    if version is None:
        raise ValueError("流程应用缺少流程版本")
    data = serialize_process_app(app, version)
    if current_version is None:
        data["version_id"] = None
        data["version_number"] = None
        data["version_status"] = None
        data["published_at"] = None
    data["draft_version_number"] = draft_version.version_number if draft_version else None
    data["has_draft"] = draft_version is not None
    return data
