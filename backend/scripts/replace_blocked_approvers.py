"""Route approval steps away from people who cannot log in.

Approvers whose login account is disabled (e.g. the legacy demo approvers imported
by merge_user_tables.py) are replaced by the platform admin in:
  * the live (current published) version of each process app, edited in place —
    legacy-format flows cannot be republished through the editor;
  * legacy flow templates used by the old approval types.
Requests keep their own flow snapshot, so history and in-flight requests are
unaffected. Optionally removes the stray draft left by an earlier failed
republish (only if it exactly matches the replaced flow and nothing uses it).

Dry run by default; --apply writes in one transaction and verifies before commit.

    .venv\\Scripts\\python.exe scripts\\replace_blocked_approvers.py
    .venv\\Scripts\\python.exe scripts\\replace_blocked_approvers.py --apply \\
        --expect-versions 3 --expect-templates 3 --expect-drafts 1
"""

# ruff: noqa: E402

import argparse
import copy
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approval.database import approval_engine
from app.approval.models import ApprovalRequest, FlowTemplate, ProcessApp, ProcessVersion
from app.db.database import engine
from app.db.models import User

ADMIN_EMAIL = "admin@demo.local"


class Abort(RuntimeError):
    pass


def replace_ids(value, blocked: set[str], admin_id: str):
    """Swap blocked ids for the admin anywhere they appear; dedupe id lists."""
    if isinstance(value, dict):
        return {k: replace_ids(v, blocked, admin_id) for k, v in value.items()}
    if isinstance(value, list):
        out = []
        for item in value:
            item = replace_ids(item, blocked, admin_id)
            if not (isinstance(item, str) and item in out):
                out.append(item)
        return out
    return admin_id if isinstance(value, str) and value in blocked else value


def mentions(value, ids: set[str]) -> set[str]:
    text = json.dumps(value)
    return {i for i in ids if i in text}


def run(args) -> dict:
    shared = approval_engine is engine
    main_db = Session(engine)
    approval_db = main_db if shared else Session(approval_engine)
    try:
        admin = main_db.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if admin is None or not admin.is_active:
            raise Abort(f"{ADMIN_EMAIL} missing or inactive")
        blocked = set(main_db.scalars(select(User.id).where(User.is_active.is_(False))).all())

        versions, drafts = [], []
        for app in approval_db.scalars(select(ProcessApp).order_by(ProcessApp.id)).all():
            current = approval_db.get(ProcessVersion, app.current_version_id) if app.current_version_id else None
            if current is None or current.status != "published" or not mentions(current.flow_schema, blocked):
                continue
            replaced = replace_ids(copy.deepcopy(current.flow_schema), blocked, admin.id)
            versions.append((app, current, replaced))
            if args.drop_stray_drafts:
                for draft in approval_db.scalars(
                    select(ProcessVersion).where(
                        ProcessVersion.process_app_id == app.id, ProcessVersion.status == "draft"
                    )
                ).all():
                    used = approval_db.scalar(
                        select(ApprovalRequest.id).where(ApprovalRequest.process_version_id == draft.id)
                    )
                    if draft.flow_schema == replaced and draft.form_schema == current.form_schema and used is None:
                        drafts.append(draft)
        templates = [
            (t, replace_ids(copy.deepcopy(t.nodes), blocked, admin.id))
            for t in approval_db.scalars(select(FlowTemplate).order_by(FlowTemplate.id)).all()
            if mentions(t.nodes, blocked)
        ]
        report = {
            "database": engine.dialect.name,
            "single_transaction": shared,
            "blocked_approvers": len(blocked),
            "versions": [f"app #{a.id} {a.name} v{v.version_number}" for a, v, _ in versions],
            "templates": [f"template #{t.id} {t.name}" for t, _ in templates],
            "stray_drafts": [f"app #{d.process_app_id} v{d.version_number} (id {d.id})" for d in drafts],
        }
        expected = {"versions": args.expect_versions, "templates": args.expect_templates, "stray_drafts": args.expect_drafts}
        wrong = {k: (v, len(report[k])) for k, v in expected.items() if v is not None and v != len(report[k])}
        if wrong:
            raise Abort(f"counts do not match expectations (expected, actual): {wrong}")
        if not args.apply:
            report["mode"] = "dry-run"
            return report

        for _, version, replaced in versions:
            version.flow_schema = replaced
        for template, replaced in templates:
            template.nodes = replaced
        for draft in drafts:
            approval_db.delete(draft)
        approval_db.flush()

        for _, version, _ in versions:
            if mentions(version.flow_schema, blocked):
                raise Abort(f"version {version.id} still references blocked approvers")
        for template, _ in templates:
            if mentions(template.nodes, blocked):
                raise Abort(f"template {template.id} still references blocked approvers")
        approval_db.commit()
        if not shared:
            main_db.commit()
        report["mode"] = "applied"
        return report
    except Exception:
        approval_db.rollback()
        if not shared:
            main_db.rollback()
        raise
    finally:
        approval_db.close()
        if not shared:
            main_db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--drop-stray-drafts", action="store_true", default=True)
    parser.add_argument("--keep-drafts", dest="drop_stray_drafts", action="store_false")
    parser.add_argument("--expect-versions", type=int)
    parser.add_argument("--expect-templates", type=int)
    parser.add_argument("--expect-drafts", type=int)
    args = parser.parse_args(argv)
    try:
        report = run(args)
    except Exception as exc:
        print(f"ABORTED, nothing committed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
