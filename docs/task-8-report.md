# Task 8 Report: Process Application List and Lifecycle UI

## Scope

Implemented the administrator process-application list and lifecycle surface only. Legacy template view files remain in place for the later cleanup task.

## Delivered

- Added `AdminProcessApps` with Ant Design Vue table, responsive horizontal scrolling, seeded process-app rows from the API, search, status/category filters, and loading/error/retry/empty states.
- Added `ProcessStatusTag` for draft, published, and inactive status presentation.
- Added accessible action buttons and dropdown actions for preview, edit, copy, and deactivate.
- Added deactivate confirmation and API error feedback. Copy inserts the returned app and navigates to its future edit route, relying on the backend for unique codes.
- Replaced active navigation entries for the legacy approval type, form template, flow template, and approval log routes with the unified process-app entry. Legacy files were not deleted.
- Added compile-safe `/admin/process-apps/new` and `/admin/process-apps/:id/edit` route stubs for Task 9.
- Expanded `process-app.spec.ts` with isolated mocked process-app list/lifecycle coverage.

## TDD Evidence

- RED: the new list/lifecycle E2E failed before implementation because `/admin/process-apps` had no page and the expected loading error state did not exist.
- GREEN: focused E2E passed after implementation.

## Verification

- `npm.cmd run typecheck` passed.
- `npm.cmd run build` passed. Vite reported only the existing large-chunk warning.
- `npm.cmd run test:e2e -- process-app.spec.ts` passed: 7 tests.
- `git diff --check` passed.

## Commit Scope

Only the Task 8 page, status component, route/layout changes, focused E2E changes, and this report are intended for the Task 8 commit.
