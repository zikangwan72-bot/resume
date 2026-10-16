from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.approval.engine import resolve_execution_path
from app.approval.form_validation import (
    _form_data_error,
    _validate_form_data,
)
from app.approval.models import (
    ApprovalAction,
    ApprovalNode,
    ApprovalRequest,
    ApprovalReturnContext,
    ApprovalType,
    ApprovalUser,
    FlowTemplate,
    FormTemplate,
    ProcessApp,
    ProcessVersion,
)
from app.approval.request_schemas import (
    ApproveRejectBody,
    ResubmitBody,
    SubmitRequest,
    TransferBody,
)
from app.approval.request_views import (
    _request_detail,
)
from app.db.models import User


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
    if db.scalar(
        select(ApprovalReturnContext.id).where(
            ApprovalReturnContext.request_id == request.id,
            ApprovalReturnContext.target_user_id == user.id,
            ApprovalReturnContext.status == "active",
        )
    ) is not None:
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


def _is_countersign_node(node: dict) -> bool:
    return (
        node.get("type") in {"countersign", "counter_sign"}
        or node.get("approval_type") == "counter_sign"
    )


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
    db: Session,
    node: ApprovalNode,
    expected_approver_id: str,
    status_value: str,
    comment: str,
    now: datetime,
) -> bool:
    result = db.execute(
        update(ApprovalNode)
        .where(
            ApprovalNode.id == node.id,
            ApprovalNode.status == "pending",
            ApprovalNode.approver_id == expected_approver_id,
        )
        .values(status=status_value, comment=comment, acted_at=now)
    )
    return result.rowcount == 1


def _active_return_context(db: Session, request_id: int) -> ApprovalReturnContext | None:
    return db.scalar(
        select(ApprovalReturnContext)
        .where(
            ApprovalReturnContext.request_id == request_id,
            ApprovalReturnContext.status == "active",
        )
        .order_by(desc(ApprovalReturnContext.created_at), desc(ApprovalReturnContext.id))
    )


def _return_target(
    db: Session,
    request: ApprovalRequest,
    source_node_index: int,
) -> tuple[ApprovalUser, int | None]:
    previous_indexes = sorted(
        {
            int(node["index"])
            for node in request.flow_snapshot
            if isinstance(node, dict)
            and isinstance(node.get("index"), int)
            and node["index"] < source_node_index
        }
    )
    if previous_indexes:
        previous_index = previous_indexes[-1]
        action = db.scalar(
            select(ApprovalAction)
            .join(ApprovalNode, ApprovalAction.node_id == ApprovalNode.id)
            .where(
                ApprovalAction.request_id == request.id,
                ApprovalAction.action == "approve",
                ApprovalNode.node_index == previous_index,
            )
            .order_by(desc(ApprovalAction.created_at), desc(ApprovalAction.id))
        )
        if action:
            actor = db.get(ApprovalUser, action.actor_id)
            if actor and actor.is_active:
                return actor, previous_index
    applicant = db.get(ApprovalUser, request.applicant_id)
    if not applicant or not applicant.is_active:
        raise HTTPException(status_code=400, detail="返工接收人不存在或已停用")
    return applicant, None


def _snapshot_flow(path: list[dict]) -> list[dict]:
    return [{**deepcopy(node), "index": index} for index, node in enumerate(path)]


def _add_runtime_nodes(db: Session, request: ApprovalRequest, flow_snapshot: list[dict]) -> None:
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
    if version is None or version.process_app_id != app.id or version.status != "published":
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


def submit_request(body: SubmitRequest, user: User, db: Session) -> dict[str, Any]:
    if body.process_app_id is not None:
        return _submit_process_app_request(body, user, db)
    return _submit_legacy_request(body, user, db)


def _submit_process_app_request(body: SubmitRequest, user: User, db: Session) -> dict[str, Any]:
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
            "email": applicant.email,
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


def resubmit_returned_request(request_id: int, body: ResubmitBody, user: User, db: Session) -> dict[str, Any]:
    request = db.get(ApprovalRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="申请不存在")
    context = _active_return_context(db, request_id)
    if request.status != "revision" or not context:
        raise HTTPException(status_code=400, detail="申请当前不处于返工状态")
    if context.target_user_id != user.id:
        raise HTTPException(status_code=403, detail="您不是本次返工处理人")
    if not isinstance(request.form_schema_snapshot, dict):
        raise HTTPException(status_code=400, detail="申请表单快照不可用")
    _validate_form_data(body.form_data, request.form_schema_snapshot)

    now = datetime.now(UTC)
    restored = db.execute(
        update(ApprovalNode)
        .where(
            ApprovalNode.request_id == request.id,
            ApprovalNode.node_index == context.source_node_index,
            ApprovalNode.status == "returned",
        )
        .values(status="pending", comment=None, acted_at=None)
    )
    if restored.rowcount < 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="返工节点状态已变化，请刷新后重试")
    request_update = db.execute(
        update(ApprovalRequest)
        .where(
            ApprovalRequest.id == request.id,
            ApprovalRequest.status == "revision",
            ApprovalRequest.current_node_index == context.source_node_index,
        )
        .values(status="pending", form_data=deepcopy(body.form_data), updated_at=now)
    )
    context_update = db.execute(
        update(ApprovalReturnContext)
        .where(
            ApprovalReturnContext.id == context.id,
            ApprovalReturnContext.status == "active",
        )
        .values(status="completed", completed_at=now)
    )
    if request_update.rowcount != 1 or context_update.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="返工状态已变化，请刷新后重试")
    source_node = db.scalar(
        select(ApprovalNode)
        .where(
            ApprovalNode.request_id == request.id,
            ApprovalNode.node_index == context.source_node_index,
        )
        .order_by(ApprovalNode.id)
    )
    db.add(
        ApprovalAction(
            node_id=source_node.id if source_node else 0,
            request_id=request.id,
            actor_id=user.id,
            actor_name=user.display_name,
            action="resubmit",
            comment=(
                body.comment.strip()
                if body.comment and body.comment.strip()
                else "修改后重新提交"
            ),
        )
    )
    db.commit()
    request = db.get(ApprovalRequest, request.id)
    return {"data": _request_detail(request, db)}


def return_node(node_id: int, body: ApproveRejectBody, user: User, db: Session) -> dict[str, Any]:
    if not body.comment.strip():
        raise HTTPException(status_code=400, detail="退回必须填写原因")
    node = db.get(ApprovalNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    if node.approver_id != user.id:
        raise HTTPException(status_code=403, detail="您不是该节点的审批人")
    if node.status != "pending":
        raise HTTPException(status_code=400, detail="该节点已被处理，不可退回")
    request = _current_request_for_node(db, node)
    if _active_return_context(db, request.id):
        raise HTTPException(status_code=409, detail="申请已在返工中")
    target, target_node_index = _return_target(db, request, node.node_index)
    now = datetime.now(UTC)
    request_update = db.execute(
        update(ApprovalRequest)
        .where(
            ApprovalRequest.id == request.id,
            ApprovalRequest.status == "pending",
            ApprovalRequest.current_node_index == node.node_index,
        )
        .values(status="revision", updated_at=now)
    )
    returned_nodes = db.execute(
        update(ApprovalNode)
        .where(
            ApprovalNode.request_id == request.id,
            ApprovalNode.node_index == node.node_index,
            ApprovalNode.status.in_(["pending", "approved"]),
        )
        .values(status="returned", comment=body.comment.strip(), acted_at=now)
    )
    if request_update.rowcount != 1 or returned_nodes.rowcount < 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="申请状态已变化，无法退回")
    context = ApprovalReturnContext(
        request_id=request.id,
        source_node_index=node.node_index,
        target_node_index=target_node_index,
        target_user_id=target.id,
        target_user_name=target.display_name,
        reason=body.comment.strip(),
        status="active",
    )
    db.add(context)
    db.add(
        ApprovalAction(
            node_id=node.id,
            request_id=request.id,
            actor_id=user.id,
            actor_name=user.display_name,
            action="return",
            comment=body.comment.strip(),
        )
    )
    db.commit()
    request = db.get(ApprovalRequest, request.id)
    return {"data": _request_detail(request, db)}


def approve_node(node_id: int, body: ApproveRejectBody, user: User, db: Session) -> dict[str, Any]:
    node = db.get(ApprovalNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    if node.approver_id != user.id:
        raise HTTPException(status_code=403, detail="您不是该节点的审批人")
    if node.status != "pending":
        raise HTTPException(status_code=400, detail="该节点已被处理，不可重复操作")
    request = _current_request_for_node(db, node)

    now = datetime.now(UTC)
    if not _consume_pending_node(db, node, user.id, "approved", body.comment, now):
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


def reject_node(node_id: int, body: ApproveRejectBody, user: User, db: Session) -> dict[str, Any]:
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
    if not _consume_pending_node(db, node, user.id, "rejected", body.comment, now):
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


def transfer_node(node_id: int, body: TransferBody, user: User, db: Session) -> dict[str, Any]:
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


def revoke_request(request_id: int, user: User, db: Session) -> dict[str, Any]:
    req = db.get(ApprovalRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    if req.applicant_id != user.id:
        raise HTTPException(status_code=403, detail="只能撤回自己的申请")
    now = datetime.now(UTC)
    revoked = db.execute(
        update(ApprovalRequest)
        .where(
            ApprovalRequest.id == request_id,
            ApprovalRequest.applicant_id == user.id,
            ApprovalRequest.status == "pending",
        )
        .values(status="revoked", updated_at=now)
    )
    if revoked.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="申请状态已变化，无法撤回")

    db.add(
        ApprovalAction(
            node_id=0,
            request_id=request_id,
            actor_id=user.id,
            actor_name=user.display_name,
            action="revoke",
        )
    )
    db.commit()
    req = db.get(ApprovalRequest, request_id)
    return {"data": _request_detail(req, db)}


def urge_request(request_id: int, user: User, db: Session) -> dict[str, Any]:
    req = db.get(ApprovalRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    if req.applicant_id != user.id:
        raise HTTPException(status_code=403, detail="只能催办自己的申请")
    urged = db.execute(
        update(ApprovalRequest)
        .where(
            ApprovalRequest.id == request_id,
            ApprovalRequest.applicant_id == user.id,
            ApprovalRequest.status == "pending",
        )
        .values(updated_at=datetime.now(UTC))
    )
    if urged.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="申请状态已变化，无法催办")

    db.add(
        ApprovalAction(
            node_id=0,
            request_id=request_id,
            actor_id=user.id,
            actor_name=user.display_name,
            action="urge",
        )
    )
    db.commit()
    req = db.get(ApprovalRequest, request_id)
    return {"data": _request_detail(req, db)}
