from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.approval.database import get_approval_db
from app.approval.models import (
    ApprovalAction,
    ApprovalNode,
    ApprovalRequest,
    ApprovalType,
    ApprovalUser,
    FlowTemplate,
    FormTemplate,
)
from app.core.security import require_permission
from app.db.models import User

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


# ── Pydantic schemas ──


class SubmitRequest(BaseModel):
    type_id: int
    title: str
    form_data: dict


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
        "applicant_id": request.applicant_id,
        "applicant_name": request.applicant_name,
        "title": request.title,
        "form_data": request.form_data,
        "status": request.status,
        "current_node_index": request.current_node_index,
        "flow_snapshot": request.flow_snapshot,
        "nodes": [
            {
                "id": n.id,
                "node_index": n.node_index,
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


# ── Endpoints ──


@router.get("/types")
def list_types(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    rows = db.scalars(select(ApprovalType).where(ApprovalType.is_active)).all()
    return {"data": [_type_with_form(r, db) for r in rows]}


@router.post("/requests")
def submit_request(
    body: SubmitRequest,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
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
        n.get("type") == "counter_sign" and n["index"] == node.node_index
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
