
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.approval.models import (
    ApprovalAction,
    ApprovalNode,
    ApprovalRequest,
    ApprovalReturnContext,
    ApprovalType,
    FormTemplate,
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


def _request_payload(
    request: ApprovalRequest,
    nodes: list[ApprovalNode],
    actions: list[ApprovalAction],
    return_context: ApprovalReturnContext | None,
) -> dict:
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
        "return_context": {
            "id": return_context.id,
            "source_node_index": return_context.source_node_index,
            "target_node_index": return_context.target_node_index,
            "target_user_id": return_context.target_user_id,
            "target_user_name": return_context.target_user_name,
            "reason": return_context.reason,
            "status": return_context.status,
            "created_at": return_context.created_at.isoformat(),
        }
        if return_context
        else None,
        "created_at": request.created_at.isoformat(),
        "updated_at": request.updated_at.isoformat(),
        "submitted_at": request.submitted_at.isoformat() if request.submitted_at else None,
        "completed_at": request.completed_at.isoformat() if request.completed_at else None,
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
    return_context = db.scalar(
        select(ApprovalReturnContext)
        .where(
            ApprovalReturnContext.request_id == request.id,
            ApprovalReturnContext.status == "active",
        )
        .order_by(desc(ApprovalReturnContext.created_at), desc(ApprovalReturnContext.id))
    )
    return _request_payload(request, nodes, actions, return_context)


def _request_details(requests: list[ApprovalRequest], db: Session) -> list[dict]:
    if not requests:
        return []
    request_ids = [request.id for request in requests]
    nodes_by_request: dict[int, list[ApprovalNode]] = {request_id: [] for request_id in request_ids}
    actions_by_request: dict[int, list[ApprovalAction]] = {
        request_id: [] for request_id in request_ids
    }
    contexts_by_request: dict[int, ApprovalReturnContext] = {}
    for node in db.scalars(
        select(ApprovalNode)
        .where(ApprovalNode.request_id.in_(request_ids))
        .order_by(ApprovalNode.request_id, ApprovalNode.node_index, ApprovalNode.id)
    ).all():
        nodes_by_request[node.request_id].append(node)
    for action in db.scalars(
        select(ApprovalAction)
        .where(ApprovalAction.request_id.in_(request_ids))
        .order_by(ApprovalAction.request_id, desc(ApprovalAction.created_at))
    ).all():
        actions_by_request[action.request_id].append(action)
    for context in db.scalars(
        select(ApprovalReturnContext)
        .where(
            ApprovalReturnContext.request_id.in_(request_ids),
            ApprovalReturnContext.status == "active",
        )
        .order_by(
            ApprovalReturnContext.request_id,
            desc(ApprovalReturnContext.created_at),
            desc(ApprovalReturnContext.id),
        )
    ).all():
        contexts_by_request.setdefault(context.request_id, context)
    return [
        _request_payload(
            request,
            nodes_by_request[request.id],
            actions_by_request[request.id],
            contexts_by_request.get(request.id),
        )
        for request in requests
    ]
