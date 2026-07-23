from copy import deepcopy
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import desc, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.approval.database import get_approval_db
from app.approval.engine import resolve_execution_path
from app.approval.models import (
    ApprovalAction,
    ApprovalNode,
    ApprovalRequest,
    ApprovalType,
    ApprovalUser,
    FlowTemplate,
    FormTemplate,
    ProcessApp,
    ProcessVersion,
)
from app.approval.serializers import serialize_process_app
from app.core.security import require_permission
from app.db.models import User

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


# ── Pydantic schemas ──


class SubmitRequest(BaseModel):
    process_app_id: int | None = None
    type_id: int | None = None
    title: str
    form_data: dict
    idempotency_key: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_a_submission_target(self) -> "SubmitRequest":
        if self.process_app_id is None and self.type_id is None:
            raise ValueError("process_app_id is required")
        if self.process_app_id is not None and self.type_id is not None:
            raise ValueError("process_app_id and type_id cannot be used together")
        return self


class ApproveRejectBody(BaseModel):
    comment: str


class TransferBody(BaseModel):
    target_user_id: str


# ── Helper functions ──


def _next_node_index(flow_snapshot: list[dict], current_index: int) -> int | None:
    later_indexes = sorted(
        {node["index"] for node in flow_snapshot if node["index"] > current_index}
    )
    return later_indexes[0] if later_indexes else None


def _current_request_for_node(db: Session, node: ApprovalNode) -> ApprovalRequest:
    request = db.get(ApprovalRequest, node.request_id)
    if not request:
        raise HTTPException(status_code=500, detail="申请数据异常")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="申请已结束，不能继续处理")
    if node.node_index != request.current_node_index:
        raise HTTPException(status_code=400, detail="该节点还未轮到处理")
    return request


def _can_view_request(request: ApprovalRequest, user: User, db: Session) -> bool:
    if request.applicant_id == user.id or "approval:manage" in user.permissions:
        return True
    return (
        db.scalar(
            select(ApprovalNode.id).where(
                ApprovalNode.request_id == request.id,
                ApprovalNode.approver_id == user.id,
            )
        )
        is not None
    )


def _type_with_form(approval_type: ApprovalType, db: Session) -> dict:
    form = db.get(FormTemplate, approval_type.form_template_id)
    return {
        "id": approval_type.id,
        "name": approval_type.name,
        "description": approval_type.description,
        "is_active": approval_type.is_active,
        "form_template": {
            "id": form.id,
            "name": form.name,
            "fields": form.fields,
        }
        if form
        else None,
    }


def _request_detail(request: ApprovalRequest, db: Session) -> dict:
    nodes = db.scalars(
        select(ApprovalNode)
        .where(ApprovalNode.request_id == request.id)
        .order_by(ApprovalNode.node_index, ApprovalNode.id)
    ).all()
    actions = db.scalars(
        select(ApprovalAction)
        .where(ApprovalAction.request_id == request.id)
        .order_by(desc(ApprovalAction.created_at))
    ).all()
    return {
        "id": request.id,
        "type_id": request.type_id,
        "process_app_id": request.process_app_id,
        "process_version_id": request.process_version_id,
        "applicant_id": request.applicant_id,
        "applicant_name": request.applicant_name,
        "applicant_snapshot": request.applicant_snapshot,
        "title": request.title,
        "form_data": request.form_data,
        "form_schema_snapshot": request.form_schema_snapshot,
        "idempotency_key": request.idempotency_key,
        "status": request.status,
        "current_node_index": request.current_node_index,
        "flow_snapshot": request.flow_snapshot,
        "nodes": [
            {
                "id": n.id,
                "node_index": n.node_index,
                "node_key": n.node_key,
                "timeout_hours": n.timeout_hours,
                "approver_id": n.approver_id,
                "approver_name": n.approver_name,
                "status": n.status,
                "comment": n.comment,
                "acted_at": n.acted_at.isoformat() if n.acted_at else None,
            }
            for n in nodes
        ],
        "actions": [
            {
                "id": a.id,
                "node_id": a.node_id,
                "actor_id": a.actor_id,
                "actor_name": a.actor_name,
                "action": a.action,
                "comment": a.comment,
                "created_at": a.created_at.isoformat(),
            }
            for a in actions
        ],
        "created_at": request.created_at.isoformat(),
        "updated_at": request.updated_at.isoformat(),
        "submitted_at": request.submitted_at.isoformat() if request.submitted_at else None,
        "completed_at": request.completed_at.isoformat() if request.completed_at else None,
    }


def _is_empty_value(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or value == []


def _form_data_error(message: str, field_id: str | None = None) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "invalid_form_data", "message": message, "field_id": field_id},
    )


def _validate_form_data(form_data: dict, form_schema: dict) -> None:
    fields = form_schema.get("fields") if isinstance(form_schema, dict) else None
    if not isinstance(fields, list):
        raise _form_data_error("流程表单定义无效")
    field_definitions: dict[str, dict] = {}
    for field in fields:
        if not isinstance(field, dict):
            raise _form_data_error("流程表单定义无效")
        field_id = field.get("id", field.get("key"))
        field_type = field.get("type")
        if not isinstance(field_id, str) or not field_id.strip() or field_type == "section":
            continue
        field_definitions[field_id] = field
    for field_id in form_data:
        if field_id not in field_definitions:
            raise _form_data_error("提交了未定义字段", field_id)
    for field_id, field in field_definitions.items():
        _validate_field_value(field, form_data.get(field_id), field_id)


def _validate_field_value(field: dict, value: object, field_id: str) -> None:
    label = field.get("label", field_id)
    field_type = field.get("type")
    if field.get("required") and _is_empty_value(value):
        raise _form_data_error(f"请填写：{label}", field_id)
    if _is_empty_value(value):
        return
    if field_type in {"number", "money"}:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise _form_data_error(f"{label}必须是数字", field_id)
    elif field_type in {"text", "textarea", "user", "department"}:
        if not isinstance(value, str):
            raise _form_data_error(f"{label}格式不正确", field_id)
    elif field_type == "date":
        _validate_date(value, field_id, label)
    elif field_type == "date_range":
        _validate_date_range(value, field_id, label)
    elif field_type in {"radio", "select"}:
        _validate_option(value, field, field_id, label)
    elif field_type == "checkbox":
        if not isinstance(value, list):
            raise _form_data_error(f"{label}必须是列表", field_id)
        for option in value:
            _validate_option(option, field, field_id, label)
    elif field_type == "attachment":
        if not isinstance(value, str) and not (
            isinstance(value, list) and all(isinstance(item, str) for item in value)
        ):
            raise _form_data_error(f"{label}格式不正确", field_id)
    elif field_type == "detail_table":
        _validate_detail_table(value, field, field_id, label)
    else:
        raise _form_data_error(f"{label}字段类型不受支持", field_id)


def _validate_option(value: object, field: dict, field_id: str, label: object) -> None:
    options = field.get("options")
    if options is not None and (not isinstance(options, list) or value not in options):
        raise _form_data_error(f"{label}选项无效", field_id)


def _validate_date(value: object, field_id: str, label: object) -> date:
    if not isinstance(value, str):
        raise _form_data_error(f"{label}必须是日期", field_id)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _form_data_error(f"{label}日期格式不正确", field_id) from exc


def _validate_date_range(value: object, field_id: str, label: object) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise _form_data_error(f"{label}必须包含开始和结束日期", field_id)
    start = _validate_date(value[0], field_id, label)
    end = _validate_date(value[1], field_id, label)
    if start > end:
        raise _form_data_error(f"{label}结束日期不能早于开始日期", field_id)


def _validate_detail_table(value: object, field: dict, field_id: str, label: object) -> None:
    if not isinstance(value, list):
        raise _form_data_error(f"{label}必须是明细行列表", field_id)
    columns = field.get("columns")
    if not isinstance(columns, list):
        raise _form_data_error(f"{label}列定义无效", field_id)
    column_definitions: dict[str, dict] = {}
    for column in columns:
        if not isinstance(column, dict):
            raise _form_data_error(f"{label}列定义无效", field_id)
        column_id = column.get("id", column.get("key"))
        if not isinstance(column_id, str) or not column_id.strip():
            raise _form_data_error(f"{label}列定义无效", field_id)
        column_definitions[column_id] = column
    for row_index, row in enumerate(value):
        row_field_id = f"{field_id}.{row_index}"
        if not isinstance(row, dict):
            raise _form_data_error(f"{label}每行必须是对象", row_field_id)
        for column_id in row:
            if column_id not in column_definitions:
                raise _form_data_error("提交了未定义明细字段", f"{row_field_id}.{column_id}")
        for column_id, column in column_definitions.items():
            _validate_field_value(column, row.get(column_id), f"{row_field_id}.{column_id}")


def _is_countersign_node(node: dict) -> bool:
    return node.get("type") in {"countersign", "counter_sign"} or node.get(
        "approval_type"
    ) == "counter_sign"


def _flow_node_at_index(request: ApprovalRequest, node_index: int) -> dict | None:
    return next(
        (
            node
            for node in request.flow_snapshot
            if isinstance(node, dict) and node.get("index") == node_index
        ),
        None,
    )


def _consume_pending_node(
    db: Session, node: ApprovalNode, status_value: str, comment: str, now: datetime
) -> bool:
    result = db.execute(
        update(ApprovalNode)
        .where(ApprovalNode.id == node.id, ApprovalNode.status == "pending")
        .values(status=status_value, comment=comment, acted_at=now)
    )
    return result.rowcount == 1


def _snapshot_flow(path: list[dict]) -> list[dict]:
    return [{**deepcopy(node), "index": index} for index, node in enumerate(path)]


def _add_runtime_nodes(
    db: Session, request: ApprovalRequest, flow_snapshot: list[dict]
) -> None:
    for node_def in flow_snapshot:
        approver_ids = (
            node_def.get("approver_ids", [])
            if _is_countersign_node(node_def)
            else [node_def.get("approver_id")]
        )
        if not isinstance(approver_ids, list) or not approver_ids:
            raise HTTPException(status_code=400, detail="流程审批人配置无效")
        for approver_id in approver_ids:
            if not isinstance(approver_id, str):
                raise HTTPException(status_code=400, detail="流程审批人配置无效")
            approver = db.get(ApprovalUser, approver_id)
            if approver is None or not approver.is_active:
                raise HTTPException(status_code=400, detail="流程审批人不存在或已停用")
            db.add(
                ApprovalNode(
                    request_id=request.id,
                    node_index=node_def["index"],
                    node_key=node_def.get("id"),
                    timeout_hours=node_def.get("timeout_hours", 0) or 0,
                    approver_id=approver.id,
                    approver_name=approver.display_name,
                    status="pending",
                )
            )


def _published_version(db: Session, process_app_id: int) -> tuple[ProcessApp, ProcessVersion]:
    app = db.get(ProcessApp, process_app_id)
    if app is None or app.status != "published" or app.current_version_id is None:
        raise HTTPException(status_code=400, detail="流程应用不存在、未发布或已停用")
    version = db.get(ProcessVersion, app.current_version_id)
    if (
        version is None
        or version.process_app_id != app.id
        or version.status != "published"
    ):
        raise HTTPException(status_code=400, detail="流程应用的已发布版本不可用")
    return app, version


def _existing_idempotent_request(
    db: Session, applicant_id: str, idempotency_key: str
) -> ApprovalRequest | None:
    return db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.applicant_id == applicant_id,
            ApprovalRequest.idempotency_key == idempotency_key,
        )
    )


# ── Endpoints ──


@router.get("/types")
def list_types(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    rows = db.scalars(select(ApprovalType).where(ApprovalType.is_active)).all()
    return {"data": [_type_with_form(r, db) for r in rows]}


@router.get("/apps")
def list_apps(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    apps = db.scalars(
        select(ProcessApp)
        .where(ProcessApp.status == "published")
        .order_by(ProcessApp.name, ProcessApp.id)
    ).all()
    result = []
    for app in apps:
        if app.current_version_id is None:
            continue
        version = db.get(ProcessVersion, app.current_version_id)
        if version and version.process_app_id == app.id and version.status == "published":
            result.append(serialize_process_app(app, version))
    return {"data": result}


@router.post("/requests", status_code=status.HTTP_201_CREATED)
def submit_request(
    body: SubmitRequest,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    if body.process_app_id is not None:
        return _submit_process_app_request(body, user, db)
    return _submit_legacy_request(body, user, db)


def _submit_process_app_request(
    body: SubmitRequest, user: User, db: Session
) -> dict[str, Any]:
    if not body.idempotency_key or not body.idempotency_key.strip():
        raise _form_data_error("幂等键不能为空")
    if not body.title.strip():
        raise _form_data_error("申请标题不能为空")

    existing = _existing_idempotent_request(db, user.id, body.idempotency_key)
    if existing is not None:
        return JSONResponse(content={"data": _request_detail(existing, db)}, status_code=200)

    app, version = _published_version(db, body.process_app_id)
    _validate_form_data(body.form_data, version.form_schema)
    try:
        resolved_path = resolve_execution_path(body.form_data, version.flow_schema)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"流程定义不可执行：{exc}") from exc
    if not resolved_path:
        raise HTTPException(status_code=400, detail="流程没有可执行的审批节点")

    applicant = db.get(ApprovalUser, user.id)
    if applicant is None or not applicant.is_active:
        raise HTTPException(status_code=400, detail="申请人不存在或已停用")

    now = datetime.now(UTC)
    flow_snapshot = _snapshot_flow(resolved_path)
    request = ApprovalRequest(
        process_app_id=app.id,
        process_version_id=version.id,
        applicant_id=applicant.id,
        applicant_name=applicant.display_name,
        applicant_snapshot={
            "id": applicant.id,
            "display_name": applicant.display_name,
            "department": applicant.department,
            "position": applicant.position,
        },
        title=body.title.strip(),
        form_data=deepcopy(body.form_data),
        form_schema_snapshot=deepcopy(version.form_schema),
        idempotency_key=body.idempotency_key,
        status="pending",
        current_node_index=0,
        flow_snapshot=flow_snapshot,
        submitted_at=now,
        updated_at=now,
    )
    db.add(request)
    try:
        db.flush()
        _add_runtime_nodes(db, request, flow_snapshot)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = _existing_idempotent_request(db, user.id, body.idempotency_key)
        if existing is not None:
            return JSONResponse(content={"data": _request_detail(existing, db)}, status_code=200)
        raise HTTPException(status_code=409, detail="审批申请创建冲突，请重试") from exc
    except HTTPException:
        db.rollback()
        raise
    db.refresh(request)
    return {"data": _request_detail(request, db)}


def _submit_legacy_request(body: SubmitRequest, user: User, db: Session) -> dict[str, Any]:
    if body.type_id is None:
        raise HTTPException(status_code=422, detail="缺少流程应用")
    approval_type = db.get(ApprovalType, body.type_id)
    if not approval_type or not approval_type.is_active:
        raise HTTPException(status_code=400, detail="审批类型不存在或已停用")
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="申请标题不能为空")

    flow = db.get(FlowTemplate, approval_type.flow_template_id)
    if not flow or not flow.is_active or not flow.nodes:
        raise HTTPException(status_code=500, detail="流程模板缺失")

    form = db.get(FormTemplate, approval_type.form_template_id)
    if form and form.is_active:
        for field in form.fields:
            key = field.get("key")
            if field.get("required") and not body.form_data.get(key):
                raise HTTPException(status_code=400, detail=f"请填写：{field.get('label', key)}")

    flow_nodes = flow.nodes
    now = datetime.now(UTC)

    request = ApprovalRequest(
        type_id=body.type_id,
        applicant_id=user.id,
        applicant_name=user.display_name,
        title=body.title,
        form_data=body.form_data,
        status="pending",
        current_node_index=0,
        flow_snapshot=flow_nodes,
        submitted_at=now,
        updated_at=now,
    )
    db.add(request)
    db.flush()

    for node_def in flow_nodes:
        if node_def.get("type") == "counter_sign":
            for approver_id in node_def.get("approver_ids", []):
                approver = db.get(ApprovalUser, approver_id)
                db.add(
                    ApprovalNode(
                        request_id=request.id,
                        node_index=node_def["index"],
                        approver_id=approver_id,
                        approver_name=approver.display_name if approver else "未知",
                        status="pending",
                    )
                )
        else:
            approver_id = node_def.get("approver_id", "")
            approver = db.get(ApprovalUser, approver_id) if approver_id else None
            db.add(
                ApprovalNode(
                    request_id=request.id,
                    node_index=node_def["index"],
                    approver_id=approver_id,
                    approver_name=approver.display_name if approver else "未知",
                    status="pending",
                )
            )

    db.commit()
    db.refresh(request)
    return {"data": _request_detail(request, db)}


@router.get("/requests")
def list_my_requests(
    status: str | None = None,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    stmt = select(ApprovalRequest).where(ApprovalRequest.applicant_id == user.id)
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    stmt = stmt.order_by(desc(ApprovalRequest.created_at)).limit(100)
    rows = db.scalars(stmt).all()
    return {"data": [_request_detail(r, db) for r in rows]}

@router.get("/requests/{request_id}")
def get_request(
    request_id: int,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    req = db.get(ApprovalRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    if not _can_view_request(req, user, db):
        raise HTTPException(status_code=403, detail="无权查看该申请")
    return {"data": _request_detail(req, db)}


@router.post("/nodes/{node_id}/approve")
def approve_node(
    node_id: int,
    body: ApproveRejectBody,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    node = db.get(ApprovalNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    if node.approver_id != user.id:
        raise HTTPException(status_code=403, detail="您不是该节点的审批人")
    if node.status != "pending":
        raise HTTPException(status_code=400, detail="该节点已被处理，不可重复操作")
    request = _current_request_for_node(db, node)

    now = datetime.now(UTC)
    if not _consume_pending_node(db, node, "approved", body.comment, now):
        db.rollback()
        raise HTTPException(status_code=400, detail="该节点已被处理，不可重复操作")

    db.add(
        ApprovalAction(
            node_id=node.id,
            request_id=node.request_id,
            actor_id=user.id,
            actor_name=user.display_name,
            action="approve",
            comment=body.comment,
        )
    )

    db.expire_all()
    sibling_nodes = db.scalars(
        select(ApprovalNode).where(
            ApprovalNode.request_id == request.id,
            ApprovalNode.node_index == node.node_index,
        )
    ).all()

    all_approved = all(n.status == "approved" for n in sibling_nodes)

    if not all_approved:
        db.commit()
        db.refresh(request)
        return {"data": _request_detail(request, db)}

    next_index = _next_node_index(request.flow_snapshot, node.node_index)
    request_updates: dict[str, object] = {"updated_at": now}
    if next_index is None:
        request_updates.update({"status": "approved", "completed_at": now})
    else:
        request_updates["current_node_index"] = next_index
    advanced = db.execute(
        update(ApprovalRequest)
        .where(
            ApprovalRequest.id == request.id,
            ApprovalRequest.status == "pending",
            ApprovalRequest.current_node_index == node.node_index,
        )
        .values(**request_updates)
    )
    if advanced.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="该节点已被处理，不可重复操作")
    db.commit()
    request = db.get(ApprovalRequest, request.id)
    return {"data": _request_detail(request, db)}


@router.post("/nodes/{node_id}/reject")
def reject_node(
    node_id: int,
    body: ApproveRejectBody,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    node = db.get(ApprovalNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    if node.approver_id != user.id:
        raise HTTPException(status_code=403, detail="您不是该节点的审批人")
    if node.status != "pending":
        raise HTTPException(status_code=400, detail="该节点已被处理，不可重复操作")
    if not body.comment:
        raise HTTPException(status_code=400, detail="驳回必须填写原因")

    now = datetime.now(UTC)
    request = _current_request_for_node(db, node)
    if not _consume_pending_node(db, node, "rejected", body.comment, now):
        db.rollback()
        raise HTTPException(status_code=400, detail="该节点已被处理，不可重复操作")

    flow_node = _flow_node_at_index(request, node.node_index)
    if flow_node and _is_countersign_node(flow_node):
        db.execute(
            update(ApprovalNode)
            .where(
                ApprovalNode.request_id == request.id,
                ApprovalNode.node_index == node.node_index,
                ApprovalNode.id != node.id,
                ApprovalNode.status == "pending",
            )
            .values(status="cancelled", comment=None, acted_at=now)
        )
    db.add(
        ApprovalAction(
            node_id=node.id,
            request_id=node.request_id,
            actor_id=user.id,
            actor_name=user.display_name,
            action="reject",
            comment=body.comment,
        )
    )
    rejected = db.execute(
        update(ApprovalRequest)
        .where(
            ApprovalRequest.id == request.id,
            ApprovalRequest.status == "pending",
            ApprovalRequest.current_node_index == node.node_index,
        )
        .values(status="rejected", completed_at=now, updated_at=now)
    )
    if rejected.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="该节点已被处理，不可重复操作")
    db.commit()
    request = db.get(ApprovalRequest, request.id)
    return {"data": _request_detail(request, db)}


@router.post("/nodes/{node_id}/transfer")
def transfer_node(
    node_id: int,
    body: TransferBody,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    node = db.get(ApprovalNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    if node.approver_id != user.id:
        raise HTTPException(status_code=403, detail="您不是该节点的审批人")
    if node.status != "pending":
        raise HTTPException(status_code=400, detail="该节点已被处理，不可转审")
    request = _current_request_for_node(db, node)
    flow_node = _flow_node_at_index(request, node.node_index)
    if flow_node is None or flow_node.get("allow_transfer") is not True:
        raise HTTPException(status_code=400, detail="该节点不允许转审")
    if body.target_user_id == user.id:
        raise HTTPException(status_code=400, detail="不能转审给自己")

    target = db.get(ApprovalUser, body.target_user_id)
    if not target or not target.is_active:
        raise HTTPException(status_code=400, detail="目标用户不存在或已停用")

    old_approver_name = node.approver_name
    transferred = db.execute(
        update(ApprovalNode)
        .where(
            ApprovalNode.id == node.id,
            ApprovalNode.approver_id == user.id,
            ApprovalNode.status == "pending",
        )
        .values(approver_id=target.id, approver_name=target.display_name)
    )
    if transferred.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="该节点已被处理，不可转审")

    db.add(
        ApprovalAction(
            node_id=node.id,
            request_id=node.request_id,
            actor_id=user.id,
            actor_name=user.display_name,
            action="transfer",
            comment=f"转审：{old_approver_name} → {target.display_name}",
        )
    )

    request_updated = db.execute(
        update(ApprovalRequest)
        .where(
            ApprovalRequest.id == request.id,
            ApprovalRequest.status == "pending",
            ApprovalRequest.current_node_index == node.node_index,
        )
        .values(updated_at=datetime.now(UTC))
    )
    if request_updated.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="该节点已被处理，不可转审")
    db.commit()
    request = db.get(ApprovalRequest, request.id)
    return {"data": _request_detail(request, db)}


@router.put("/requests/{request_id}/revoke")
def revoke_request(
    request_id: int,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    req = db.get(ApprovalRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    if req.applicant_id != user.id:
        raise HTTPException(status_code=403, detail="只能撤回自己的申请")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="只有待审批状态的申请可以撤回")

    req.status = "revoked"
    req.updated_at = datetime.now(UTC)

    db.add(
        ApprovalAction(
            node_id=0,
            request_id=req.id,
            actor_id=user.id,
            actor_name=user.display_name,
            action="revoke",
        )
    )
    db.commit()
    db.refresh(req)
    return {"data": _request_detail(req, db)}


@router.put("/requests/{request_id}/urge")
def urge_request(
    request_id: int,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    req = db.get(ApprovalRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    if req.applicant_id != user.id:
        raise HTTPException(status_code=403, detail="只能催办自己的申请")
    if req.status not in ("pending",):
        raise HTTPException(status_code=400, detail="当前状态不支持催办")

    req.updated_at = datetime.now(UTC)

    db.add(
        ApprovalAction(
            node_id=0,
            request_id=req.id,
            actor_id=user.id,
            actor_name=user.display_name,
            action="urge",
        )
    )
    db.commit()
    db.refresh(req)
    return {"data": _request_detail(req, db)}


@router.get("/pending")
def list_pending(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    node_rows = db.scalars(
        select(ApprovalNode)
        .where(
            ApprovalNode.approver_id == user.id,
            ApprovalNode.status == "pending",
        )
        .order_by(desc(ApprovalNode.created_at))
        .limit(100)
    ).all()

    request_ids = list({n.request_id for n in node_rows})
    requests_map = (
        {
            r.id: r
            for r in db.scalars(
                select(ApprovalRequest).where(ApprovalRequest.id.in_(request_ids))
            ).all()
        }
        if request_ids
        else {}
    )

    result = []
    for n in node_rows:
        req = requests_map.get(n.request_id)
        if req and req.status == "pending" and n.node_index == req.current_node_index:
            result.append(
                {
                    "node_id": n.id,
                    "node_index": n.node_index,
                    "request": {
                        "id": req.id,
                        "type_id": req.type_id,
                        "applicant_name": req.applicant_name,
                        "title": req.title,
                        "status": req.status,
                        "current_node_index": req.current_node_index,
                        "created_at": req.created_at.isoformat(),
                    },
                }
            )
    return {"data": result}


@router.get("/users")
def list_approval_users(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    rows = db.scalars(
        select(ApprovalUser)
        .where(ApprovalUser.is_active)
        .order_by(ApprovalUser.display_name)
    ).all()
    return {
        "data": [
            {
                "id": r.id,
                "email": r.email,
                "display_name": r.display_name,
                "department": r.department,
                "role": r.role,
            }
            for r in rows
        ]
    }


@router.get("/handled")
def list_handled(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    node_rows = db.scalars(
        select(ApprovalNode)
        .where(
            ApprovalNode.approver_id == user.id,
            ApprovalNode.status != "pending",
        )
        .order_by(desc(ApprovalNode.acted_at))
        .limit(100)
    ).all()

    request_ids = list({n.request_id for n in node_rows})
    requests_map = (
        {
            r.id: r
            for r in db.scalars(
                select(ApprovalRequest).where(ApprovalRequest.id.in_(request_ids))
            ).all()
        }
        if request_ids
        else {}
    )

    result = []
    for n in node_rows:
        req = requests_map.get(n.request_id)
        if req:
            result.append(
                {
                    "node_id": n.id,
                    "node_index": n.node_index,
                    "node_status": n.status,
                    "comment": n.comment,
                    "acted_at": n.acted_at.isoformat() if n.acted_at else None,
                    "request": {
                        "id": req.id,
                        "type_id": req.type_id,
                        "applicant_name": req.applicant_name,
                        "title": req.title,
                        "status": req.status,
                    },
                }
            )
    return {"data": result}


@router.get("/cc")
def list_cc(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    rows = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.status.in_(["approved", "rejected"]))
        .order_by(desc(ApprovalRequest.completed_at))
        .limit(50)
    ).all()
    return {"data": [_request_detail(r, db) for r in rows]}
