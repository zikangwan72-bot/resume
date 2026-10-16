from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.approval import workflow
from app.approval.database import get_approval_db
from app.approval.models import (
    ApprovalNode,
    ApprovalRequest,
    ApprovalReturnContext,
    ApprovalType,
    ApprovalUser,
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
    _request_details,
    _type_with_form,
)
from app.approval.serializers import serialize_process_app
from app.approval.workflow import (
    _can_view_request,
)
from app.core.security import require_permission
from app.db.models import User

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


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
    version_ids = [app.current_version_id for app in apps if app.current_version_id is not None]
    versions = {
        version.id: version
        for version in db.scalars(
            select(ProcessVersion).where(ProcessVersion.id.in_(version_ids))
        ).all()
    }
    result = []
    for app in apps:
        version = versions.get(app.current_version_id)
        if version and version.process_app_id == app.id and version.status == "published":
            result.append(serialize_process_app(app, version))
    return {"data": result}


@router.post("/requests", status_code=status.HTTP_201_CREATED)
def submit_request(
    body: SubmitRequest,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    return workflow.submit_request(body, user, db)


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
    return {"data": _request_details(rows, db)}


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


@router.post("/requests/{request_id}/resubmit")
def resubmit_returned_request(
    request_id: int,
    body: ResubmitBody,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    return workflow.resubmit_returned_request(request_id, body, user, db)


@router.post("/nodes/{node_id}/return")
def return_node(
    node_id: int,
    body: ApproveRejectBody,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    return workflow.return_node(node_id, body, user, db)


@router.post("/nodes/{node_id}/approve")
def approve_node(
    node_id: int,
    body: ApproveRejectBody,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    return workflow.approve_node(node_id, body, user, db)


@router.post("/nodes/{node_id}/reject")
def reject_node(
    node_id: int,
    body: ApproveRejectBody,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    return workflow.reject_node(node_id, body, user, db)


@router.post("/nodes/{node_id}/transfer")
def transfer_node(
    node_id: int,
    body: TransferBody,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    return workflow.transfer_node(node_id, body, user, db)


@router.put("/requests/{request_id}/revoke")
def revoke_request(
    request_id: int,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    return workflow.revoke_request(request_id, user, db)


@router.put("/requests/{request_id}/urge")
def urge_request(
    request_id: int,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    return workflow.urge_request(request_id, user, db)


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
    return_contexts = db.scalars(
        select(ApprovalReturnContext)
        .where(
            ApprovalReturnContext.target_user_id == user.id,
            ApprovalReturnContext.status == "active",
        )
        .order_by(desc(ApprovalReturnContext.created_at))
        .limit(100)
    ).all()
    for context in return_contexts:
        req = db.get(ApprovalRequest, context.request_id)
        if req and req.status == "revision":
            result.append(
                {
                    "node_id": 0,
                    "node_index": context.target_node_index,
                    "kind": "revision",
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


@router.get("/overview")
def approval_overview(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    pending = list_pending(user, db)["data"]
    handled_count = db.scalar(
        select(func.count(ApprovalNode.id)).where(
            ApprovalNode.approver_id == user.id,
            ApprovalNode.status != "pending",
        )
    ) or 0
    return {
        "data": {
            "pending_count": len(pending),
            "handled_count": handled_count,
            "pending_items": pending[:5],
        }
    }


@router.get("/users")
def list_approval_users(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    rows = db.scalars(
        select(ApprovalUser).where(ApprovalUser.is_active).order_by(ApprovalUser.display_name)
    ).all()
    return {
        "data": [
            {
                "id": r.id,
                "email": r.email,
                "display_name": r.display_name,
                "department": r.department,
                "position": r.position,
                "role": r.role,
                "is_active": r.is_active,
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
