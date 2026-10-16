from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import Interval, exists, func, literal_column, select
from sqlalchemy.orm import Session

from app.approval.models import (
    ApprovalNode,
    ApprovalRequest,
    ApprovalUser,
    ProcessApp,
    ProcessVersion,
)

MonitorStatus = Literal["pending", "approved", "rejected", "revoked"]


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _is_overdue(node: ApprovalNode | None, now: datetime) -> bool:
    if node is None or node.timeout_hours <= 0:
        return False
    created_at = _as_utc(node.created_at)
    return created_at is not None and now - created_at > timedelta(hours=node.timeout_hours)


def _serialize_current_approver(
    node: ApprovalNode, users: dict[str, ApprovalUser]
) -> dict:
    approver = users.get(node.approver_id)
    return {
        "id": node.approver_id,
        "name": node.approver_name,
        "email": approver.email if approver else None,
        "department": approver.department if approver else None,
        "position": approver.position if approver else None,
    }


def _monitor_item(
    request: ApprovalRequest,
    process_apps: dict[int, ProcessApp],
    versions: dict[int, ProcessVersion],
    users: dict[str, ApprovalUser],
    current_nodes: list[ApprovalNode],
    now: datetime,
) -> dict:
    node = current_nodes[0] if current_nodes else None
    process_app = process_apps.get(request.process_app_id)
    version = versions.get(request.process_version_id)
    applicant = users.get(request.applicant_id)
    applicant_snapshot = request.applicant_snapshot or {}
    flow_node = next(
        (
            item
            for item in request.flow_snapshot
            if item.get("index") == request.current_node_index
            or item.get("id") == (node.node_key if node else None)
        ),
        {},
    )
    current_approvers = [_serialize_current_approver(node, users) for node in current_nodes]
    overdue = _is_overdue(node, now)
    return {
        "id": request.id,
        "title": request.title,
        "status": request.status,
        "submitted_at": request.submitted_at.isoformat() if request.submitted_at else None,
        "created_at": request.created_at.isoformat(),
        "process_app": {
            "id": process_app.id if process_app else request.process_app_id,
            "code": process_app.code if process_app else None,
            "name": process_app.name if process_app else None,
            "version_id": version.id if version else request.process_version_id,
            "version_number": version.version_number if version else None,
        },
        "applicant": {
            "id": request.applicant_id,
            "name": request.applicant_name,
            "email": applicant.email if applicant else None,
            "department": applicant_snapshot.get("department")
            or (applicant.department if applicant else None),
            "position": applicant_snapshot.get("position")
            or (applicant.position if applicant else None),
        },
        "current_node": {
            "id": node.id if node else None,
            "node_index": request.current_node_index,
            "node_key": node.node_key if node else flow_node.get("id"),
            "name": flow_node.get("name") or flow_node.get("label"),
            "status": node.status if node else None,
            "timeout_hours": node.timeout_hours if node else 0,
            "created_at": node.created_at.isoformat() if node else None,
        },
        "current_approvers": current_approvers,
        "current_approver": current_approvers[0] if current_approvers else None,
        "overdue": overdue,
    }


def _monitor_context(
    db: Session, requests: list[ApprovalRequest]
) -> tuple[dict, dict, dict, dict[int, list[ApprovalNode]]]:
    process_ids = {
        request.process_app_id for request in requests if request.process_app_id is not None
    }
    version_ids = {
        request.process_version_id for request in requests if request.process_version_id is not None
    }
    request_ids = {request.id for request in requests}
    current_nodes_by_request: dict[int, list[ApprovalNode]] = {
        request_id: [] for request_id in request_ids
    }
    all_current_nodes = db.scalars(
        select(ApprovalNode)
        .where(ApprovalNode.request_id.in_(request_ids), ApprovalNode.status == "pending")
        .order_by(ApprovalNode.request_id, ApprovalNode.node_index, ApprovalNode.id)
    ).all()
    current_indexes = {request.id: request.current_node_index for request in requests}
    for node in all_current_nodes:
        if node.node_index == current_indexes[node.request_id]:
            current_nodes_by_request[node.request_id].append(node)
    user_ids = {request.applicant_id for request in requests}
    user_ids.update(node.approver_id for node in all_current_nodes)
    return (
        {
            item.id: item
            for item in db.scalars(
                select(ProcessApp).where(ProcessApp.id.in_(process_ids))
            ).all()
        },
        {
            item.id: item
            for item in db.scalars(
                select(ProcessVersion).where(ProcessVersion.id.in_(version_ids))
            ).all()
        },
        {
            item.id: item
            for item in db.scalars(select(ApprovalUser).where(ApprovalUser.id.in_(user_ids))).all()
        },
        current_nodes_by_request,
    )


def _current_node_exists(condition) -> object:
    return exists(
        select(ApprovalNode.id).where(
            ApprovalNode.request_id == ApprovalRequest.id,
            ApprovalNode.node_index == ApprovalRequest.current_node_index,
            ApprovalNode.status == "pending",
            condition,
        )
    )


def _overdue_condition(dialect_name: str) -> object:
    if dialect_name == "postgresql":
        one_hour = literal_column("INTERVAL '1 hour'", type_=Interval())
        return (
            ApprovalNode.created_at + ApprovalNode.timeout_hours * one_hour
            < func.current_timestamp()
        )
    return (
        func.julianday(func.current_timestamp()) - func.julianday(ApprovalNode.created_at)
        > ApprovalNode.timeout_hours / 24.0
    )


def _overdue_node_exists(db: Session) -> object:
    dialect_name = db.get_bind().dialect.name
    return _current_node_exists(
        ApprovalNode.timeout_hours > 0,
    ).where(_overdue_condition(dialect_name))


def _monitor_requests(
    db: Session,
    process_app_id: int | None,
    request_status: MonitorStatus | None,
    submitted_from: datetime | None,
    submitted_to: datetime | None,
    department: str | None,
    applicant: str | None,
    current_approver_id: str | None,
    overdue: bool | None,
    offset: int,
    limit: int,
) -> tuple[list[ApprovalRequest], int]:
    statement = select(ApprovalRequest).order_by(
        ApprovalRequest.submitted_at.desc(), ApprovalRequest.id.desc()
    )
    if process_app_id is not None:
        statement = statement.where(ApprovalRequest.process_app_id == process_app_id)
    if request_status is not None:
        statement = statement.where(ApprovalRequest.status == request_status)
    if submitted_from is not None:
        statement = statement.where(ApprovalRequest.submitted_at >= submitted_from)
    if submitted_to is not None:
        statement = statement.where(ApprovalRequest.submitted_at <= submitted_to)
    if department:
        snapshot_department = ApprovalRequest.applicant_snapshot["department"].as_string()
        statement = statement.where(
            exists(
                select(ApprovalUser.id).where(
                    ApprovalUser.id == ApprovalRequest.applicant_id,
                    func.coalesce(snapshot_department, ApprovalUser.department).contains(
                        department
                    ),
                )
            )
        )
    if applicant:
        statement = statement.where(ApprovalRequest.applicant_name.contains(applicant))
    if current_approver_id:
        statement = statement.where(
            _current_node_exists(ApprovalNode.approver_id == current_approver_id)
        )
    if overdue is True:
        statement = statement.where(_overdue_node_exists(db))
    elif overdue is False:
        statement = statement.where(~_overdue_node_exists(db))
    total = db.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    ) or 0
    page_statement = statement.offset(offset).limit(limit)
    return db.scalars(page_statement).all(), total
