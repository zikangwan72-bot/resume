from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import desc, select
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


def _reset_nodes_at_index(db: Session, request_id: int, node_index: int) -> None:
    nodes = db.scalars(
        select(ApprovalNode).where(
            ApprovalNode.request_id == request_id,
            ApprovalNode.node_index == node_index,
        )
    ).all()
    for node in nodes:
        node.status = "pending"
        node.comment = None
        node.acted_at = None


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


def _form_data_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "invalid_form_data", "message": message},
    )


def _validate_form_data(form_data: dict, form_schema: dict) -> None:
    fields = form_schema.get("fields") if isinstance(form_schema, dict) else None
    if not isinstance(fields, list):
        raise _form_data_error("流程表单定义无效")
    for field in fields:
        if not isinstance(field, dict):
            raise _form_data_error("流程表单定义无效")
        field_id = field.get("id", field.get("key"))
        field_type = field.get("type")
        if not isinstance(field_id, str) or not field_id.strip() or field_type == "section":
            continue
        value = form_data.get(field_id)
        label = field.get("label", field_id)
        if field.get("required") and _is_empty_value(value):
            raise _form_data_error(f"请填写：{label}")
        if _is_empty_value(value):
            continue
        if field_type in {"number", "money"} and (
            isinstance(value, bool) or not isinstance(value, int | float)
        ):
            raise _form_data_error(f"{label}必须是数字")
        if field_type in {
            "text",
            "textarea",
            "date",
            "user",
            "department",
            "attachment",
        } and not isinstance(value, str):
            raise _form_data_error(f"{label}格式不正确")
        if field_type in {"radio", "select"}:
            options = field.get("options")
            if options is not None and (not isinstance(options, list) or value not in options):
                raise _form_data_error(f"{label}选项无效")


def _is_countersign_node(node: dict) -> bool:
    return node.get("type") in {"countersign", "counter_sign"} or node.get(
        "approval_type"
    ) == "counter_sign"


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
    node.status = "approved"
    node.comment = body.comment
    node.acted_at = now

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

    # Counter-sign check: verify ALL nodes at this index are approved
    sibling_nodes = db.scalars(
        select(ApprovalNode).where(
            ApprovalNode.request_id == request.id,
            ApprovalNode.node_index == node.node_index,
        )
    ).all()

    all_approved = all(n.status == "approved" for n in sibling_nodes)

    if not all_approved:
        db.commit()
        db.refresh(node)
        return {"data": _request_detail(request, db)}

    # All approved at current index, advance the flow
    next_index = _next_node_index(request.flow_snapshot, node.node_index)
    if next_index is None:
        request.status = "approved"
        request.completed_at = now
    else:
        request.current_node_index = next_index
        _reset_nodes_at_index(db, request.id, next_index)
    request.updated_at = now
    db.commit()
    db.refresh(request)
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

    # Check if this is a counter-sign node
    is_counter_sign = any(
        _is_countersign_node(n) and n["index"] == node.node_index
        for n in request.flow_snapshot
    )

    if is_counter_sign:
        # Counter-sign reject: record the rejected index, then return to the previous approver.
        sibling_nodes = db.scalars(
            select(ApprovalNode).where(
                ApprovalNode.request_id == request.id,
                ApprovalNode.node_index == node.node_index,
            )
        ).all()
        for sn in sibling_nodes:
            sn.status = "rejected"
            sn.comment = sn.comment or body.comment
            sn.acted_at = sn.acted_at or now

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

        if node.node_index > 0:
            request.current_node_index = node.node_index - 1
            prev_nodes = db.scalars(
                select(ApprovalNode).where(
                    ApprovalNode.request_id == request.id,
                    ApprovalNode.node_index == node.node_index - 1,
                )
            ).all()
            for pn in prev_nodes:
                pn.status = "pending"
                pn.comment = None
                pn.acted_at = None
    else:
        # Normal reject: entire request becomes rejected
        node.status = "rejected"
        node.comment = body.comment
        node.acted_at = now
        request.status = "rejected"
        request.completed_at = now

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

    request.updated_at = now
    db.commit()
    db.refresh(request)
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

    target = db.get(ApprovalUser, body.target_user_id)
    if not target:
        raise HTTPException(status_code=400, detail="目标用户不存在")

    old_approver_name = node.approver_name
    node.approver_id = target.id
    node.approver_name = target.display_name

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

    request.updated_at = datetime.now(UTC)

    db.commit()
    db.refresh(request)
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
