# Task 8 Report: Process Application List and Lifecycle UI

## Scope

Implemented the administrator process-application list and lifecycle surface only. Legacy template view files remain in place for the later cleanup task.

## Delivered

- Added AdminProcessApps with Ant Design Vue table, responsive horizontal scrolling, seeded process-app rows from the API, search, status/category filters, and loading/error/retry/empty states.
- Added ProcessStatusTag for draft, published, and inactive status presentation.
- Added accessible action buttons and dropdown actions for preview, edit, copy, and deactivate.
- Added deactivate confirmation and API error feedback. Copy inserts the returned app and navigates to its future edit route, relying on the backend for unique codes.
- Replaced active navigation entries for the legacy approval type, form template, and flow template routes with the unified process-app entry. The approval logs route/menu remains active and legacy files were not deleted.
- Added compile-safe /admin/process-apps/new and /admin/process-apps/:id/edit route stubs for Task 9.
- Expanded process-app.spec.ts with isolated mocked process-app list/lifecycle coverage.

## Fix Evidence

- The list endpoint now serializes app.current_version_id when it points to the published version, exposes draft_version_number and has_draft, and leaves editable-version behavior unchanged for detail/edit endpoints.
- The focused E2E mock verifies a published v1 remains the displayed current version while v2 is shown as 有草稿.
- Legacy direct template routes were restored while their three menu entries remain removed; approval logs route/menu were restored.
- Focused E2E now explicitly covers loading, mobile table layout, preview, new/edit targets, and copy/deactivate API error feedback.

## Verification

- backend/.venv/Scripts/python.exe -m pytest backend/tests/test_process_admin.py -q passed.
- backend/.venv/Scripts/python.exe -m ruff check backend/app backend/tests passed.
- npm.cmd run typecheck passed.
- npm.cmd run build passed.
- npm.cmd run test:e2e -- process-app.spec.ts passed.
- git diff --check passed.
