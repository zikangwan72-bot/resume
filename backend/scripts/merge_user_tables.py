"""Reconcile users and approval_users (see app/db/user_merge.py).

Dry run by default. With --apply it writes inside one transaction (when both
model groups share a database, e.g. Supabase), verifies before committing, and
rolls everything back on any problem or count mismatch.

    .venv\\Scripts\\python.exe scripts\\merge_user_tables.py
    .venv\\Scripts\\python.exe scripts\\merge_user_tables.py --apply \\
        --expect-conflicts 1 --expect-orphans 5 --expect-missing 19
"""

# ruff: noqa: E402

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.approval.database import approval_engine
from app.approval.models import ApprovalUser
from app.db.database import engine
from app.db.models import User
from app.db.user_merge import MergeAbort, apply_merge, plan_merge, verify_merge


def counts(main_db: Session, approval_db: Session) -> dict[str, int]:
    return {
        "users": main_db.scalar(select(func.count()).select_from(User)),
        "approval_users": approval_db.scalar(select(func.count()).select_from(ApprovalUser)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--expect-conflicts", type=int)
    parser.add_argument("--expect-orphans", type=int)
    parser.add_argument("--expect-missing", type=int)
    args = parser.parse_args(argv)

    shared = approval_engine is engine
    main_db = Session(engine)
    approval_db = main_db if shared else Session(approval_engine)
    try:
        before = counts(main_db, approval_db)
        plan = plan_merge(main_db, approval_db)
        report = {"database": engine.dialect.name, "single_transaction": shared, "before": before, "plan": plan.summary()}
        expected = {
            "conflicts": args.expect_conflicts,
            "orphans_imported": args.expect_orphans,
            "approval_rows_added": args.expect_missing,
        }
        mismatched = {k: (v, plan.summary()[k]) for k, v in expected.items() if v is not None and v != plan.summary()[k]}
        if mismatched:
            raise MergeAbort(f"plan does not match expectations (expected, actual): {mismatched}")
        if not args.apply:
            report["mode"] = "dry-run"
            print(json.dumps(report, ensure_ascii=False, indent=1))
            return 0

        apply_merge(main_db, approval_db, plan)
        problems = verify_merge(main_db, approval_db)
        if problems:
            raise MergeAbort(f"verification failed before commit: {problems}")
        report["after"] = counts(main_db, approval_db)
        if not shared:
            approval_db.commit()
        main_db.commit()
        report["mode"] = "applied"
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    except Exception as exc:
        main_db.rollback()
        if not shared:
            approval_db.rollback()
        print(f"ABORTED, nothing committed: {exc}", file=sys.stderr)
        return 1
    finally:
        main_db.close()
        if not shared:
            approval_db.close()


if __name__ == "__main__":
    raise SystemExit(main())
