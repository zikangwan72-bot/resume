"""Make `users` (login accounts) the single source of identity for approvals.

The approval engine looks people up in `approval_users` by the same id as
`users.id`. Historically the two tables were seeded separately, so:
  * most login users had no approval row and could not submit approvals,
  * one id was shared by two different people,
  * some approvers existed only in `approval_users`.

`merge_user_tables` reconciles them, idempotently:
  * shared ids: the approval row takes email/name/department/role from `users`
    (users wins on conflicts); approval is_active is left alone;
  * ids only in `approval_users`: imported into `users` as disabled accounts with no
    password, so they cannot log in; their approval row is left as it is so published
    flows that route to them keep working;
  * ids only in `users`: get an approval row.
No approval history is touched; history rows reference ids, which are all preserved.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approval.models import (
    ApprovalAction,
    ApprovalNode,
    ApprovalRequest,
    ApprovalReturnContext,
    ApprovalUser,
)
from app.db.models import User

# Login roles -> approval roles (approval side only uses role for display).
APPROVAL_ROLE = {"approval_finance": "finance"}
ROLE_TITLE = {
    "platform_admin": "平台管理员",
    "department_manager": "部门经理",
    "approval_finance": "财务审批",
    "finance": "财务专员",
    "recruitment_admin": "招聘管理员",
    "asset_admin": "资产管理员",
    "it_support": "IT运维",
    "employee": "员工",
}


class MergeAbort(RuntimeError):
    """The data does not look like what the merge expects; nothing was written."""


@dataclass
class MergePlan:
    conflicts: list[str] = field(default_factory=list)  # shared id, different email
    synced: list[str] = field(default_factory=list)  # shared ids whose approval row changes
    orphans: list[str] = field(default_factory=list)  # only in approval_users -> new disabled users
    missing: list[str] = field(default_factory=list)  # only in users -> new approval rows

    def summary(self) -> dict[str, int]:
        return {
            "conflicts": len(self.conflicts),
            "synced": len(self.synced),
            "orphans_imported": len(self.orphans),
            "approval_rows_added": len(self.missing),
        }


def _approval_fields(user: User, current_position: str | None, conflict: bool) -> dict:
    # is_active is deliberately not synced: imported approvers are disabled as
    # logins but must stay active approvers, or every flow routing to them breaks.
    return {
        "email": user.email,
        "display_name": user.display_name,
        "department": user.department,
        "role": APPROVAL_ROLE.get(user.role, user.role),
        # A conflicting row's position described the other person.
        "position": ROLE_TITLE.get(user.role, user.role)
        if conflict or not current_position
        else current_position,
    }


def plan_merge(main_db: Session, approval_db: Session) -> MergePlan:
    users = {u.id: u for u in main_db.scalars(select(User)).all()}
    approval = {u.id: u for u in approval_db.scalars(select(ApprovalUser)).all()}
    plan = MergePlan()
    user_emails = {u.email.lower(): u.id for u in users.values()}
    approval_emails = {u.email.lower(): u.id for u in approval.values()}

    for user_id, row in approval.items():
        user = users.get(user_id)
        if user is None:
            other = user_emails.get(row.email.lower())
            if other is not None:
                raise MergeAbort(f"approval-only {row.email} collides with login user {other}")
            plan.orphans.append(user_id)
            continue
        conflict = user.email.lower() != row.email.lower()
        if conflict:
            plan.conflicts.append(user_id)
            holder = approval_emails.get(user.email.lower())
            if holder is not None and holder != user_id:
                raise MergeAbort(f"{user.email} already used by approval user {holder}")
        wanted = _approval_fields(user, row.position, conflict)
        if any(getattr(row, key) != value for key, value in wanted.items()):
            plan.synced.append(user_id)

    for user_id, user in users.items():
        if user_id in approval:
            continue
        holder = approval_emails.get(user.email.lower())
        if holder is not None:
            raise MergeAbort(f"{user.email} already used by approval user {holder}")
        plan.missing.append(user_id)
    return plan


def apply_merge(main_db: Session, approval_db: Session, plan: MergePlan) -> None:
    """Apply a plan from `plan_merge`. Caller owns commit/rollback."""
    users = {u.id: u for u in main_db.scalars(select(User)).all()}
    approval = {u.id: u for u in approval_db.scalars(select(ApprovalUser)).all()}
    conflicts = set(plan.conflicts)
    for user_id in plan.synced:
        row, user = approval[user_id], users[user_id]
        for key, value in _approval_fields(user, row.position, user_id in conflicts).items():
            setattr(row, key, value)
    now = datetime.now(UTC)
    for user_id in plan.orphans:
        row = approval[user_id]
        main_db.add(
            User(
                id=row.id,
                email=row.email,
                display_name=row.display_name,
                department=row.department,
                role=row.role,
                permissions=[],
                password_hash=None,
                is_active=False,
                created_at=now,
            )
        )
    for user_id in plan.missing:
        user = users[user_id]
        approval_db.add(
            ApprovalUser(
                id=user.id,
                created_at=now,
                is_active=user.is_active,
                **_approval_fields(user, None, False),
            )
        )
    main_db.flush()
    approval_db.flush()


def verify_merge(main_db: Session, approval_db: Session) -> list[str]:
    """Return problems found after a merge (empty list = consistent)."""
    problems: list[str] = []
    users = {u.id: u for u in main_db.scalars(select(User)).all()}
    approval = {u.id: u for u in approval_db.scalars(select(ApprovalUser)).all()}
    if set(users) != set(approval):
        problems.append(
            f"id sets differ: only users={sorted(set(users) - set(approval))} "
            f"only approval={sorted(set(approval) - set(users))}"
        )
    for user_id in set(users) & set(approval):
        if users[user_id].email.lower() != approval[user_id].email.lower():
            problems.append(f"email mismatch for {user_id}")
        if users[user_id].is_active and not approval[user_id].is_active:
            problems.append(f"active login user {users[user_id].email} is inactive for approvals")
    references = [
        (ApprovalRequest, ApprovalRequest.applicant_id),
        (ApprovalNode, ApprovalNode.approver_id),
        (ApprovalAction, ApprovalAction.actor_id),
        (ApprovalReturnContext, ApprovalReturnContext.target_user_id),
    ]
    for model, column in references:
        for value in approval_db.scalars(select(column).distinct()).all():
            if value and (value not in approval or value not in users):
                problems.append(f"{model.__tablename__}.{column.key}={value} has no user")
    return problems
