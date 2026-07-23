# Task 5 Report: Read-Only Process Monitoring APIs

## Scope

- Added admin-protected, read-only process monitoring summary and paginated request APIs.
- Added typed filters for process app, status, submission date range, department, applicant, current approver, and overdue state.
- Added deterministic ordering and bounded pagination.
- Added process app/version, applicant snapshot, current node, current approver, and overdue fields for the monitoring table.
- Overdue requests require a pending current node with `timeout_hours > 0` whose node age exceeds the configured timeout.
- Request-level filtering and pagination avoid duplicate rows when a current node has multiple approvers.

## Verification

TDD red phase:

```text
19 passed, 2 failed
The new monitor tests failed with 404 because the endpoints were not implemented.
```

Green phase:

```text
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_admin.py -q
21 passed in 5.73s

backend/.venv/Scripts/ruff.exe check backend/app/approval/admin_router.py backend/tests/test_process_admin.py
All checks passed!

git diff --check
No whitespace errors.
```

Only the focused admin test file and Ruff checks were run. The frontend and Task 6 were not changed.
