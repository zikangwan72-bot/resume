# Task 7 Report

## Scope

Implemented frontend approval contracts and the `/admin/users` administration page only. The process-app list and Task 8 were not changed.

## TDD Evidence

- RED: `npm.cmd run test:e2e -- process-app.spec.ts` failed because `/admin/users` had no `新增员工` control.
- GREEN: the same focused scenario passes after adding the typed user page and route.

## Delivered

- Added `frontend/src/types/approval.ts` with typed approval user, process app/version, form/flow, request detail, and monitor contracts; removed unsafe `any` from the shared approval request type.
- Added Ant Design `/admin/users` page with table, search/status filtering, loading/error/empty/retry states, create/edit modal, required validation for display name/email/department/position/role, API field/general error handling, and active-status switch confirmation.
- Replaced the legacy `/admin/roles` route/menu entry after the new page existed. No delete action is exposed.
- Added focused Playwright coverage in `frontend/tests/e2e/process-app.spec.ts`.

## Verification

- `npm.cmd run typecheck` passed.
- `npm.cmd run build` passed. Vite reported the existing large-chunk warning.
- `npm.cmd run test:e2e -- process-app.spec.ts` passed: 1 test.

## Review Fixes

- Corrected all approval contracts against backend serializers, including `MonitorPerson`, `node_key`, runtime node fields, snapshots, `idempotency_key`, and monitor current-approver structures.
- Replaced the single E2E check with five deterministic Playwright scenarios using per-test in-memory route state: seeded/filter/menu, create/validation/409, edit/status transitions, loading/error/retry/empty, and mobile smoke.
- Removed duplicate empty-state rendering, added employee names to status-switch labels, and mapped duplicate-email conflicts to the email field plus general error alert.
- Final focused E2E result: 5 tests passed.
