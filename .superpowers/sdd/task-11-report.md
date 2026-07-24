# Task 11 Report: Employee Dynamic Form and Request Details

## Implemented

- Added `DynamicApprovalForm` with typed props/events, applicant descriptions, structural sections, local/backend-aligned validation, unsupported-field alerts, ISO date serialization, choice controls, JSON-safe attachment metadata, and editable detail rows.
- Replaced the legacy `/types` request flow with published process-app selection and idempotent request submission to `/approvals/requests`.
- Updated request detail to render applicant, schema, form, and path snapshots read-only, including countersign approvers, condition nodes, timeline, and action controls.
- Added isolated Task 11 Playwright route mocks for submission/idempotency/422 retry and mobile detail/action error states.

## Verification

- PASS: `npm.cmd run typecheck`.
- PARTIAL: focused Task 11 Playwright run: detail/mobile/action-error scenario passed; purchase submission scenario failed because the Ant date input was read-only.
- FIX APPLIED: date and date-range inputs now set `input-read-only="false"`. No additional rerun was made after the bounded final E2E run.
- BLOCKED: `npm.cmd run build` still reports two pre-existing errors in `frontend/src/views/approval/AdminProcessEditor.vue` (lines 105-106, `undefined` assigned to `ProcessApp | null`). Renderer-specific build errors were fixed before the final run.

## Scope

Only Task 11 dynamic-form, request submission/detail, focused E2E coverage, and this report were changed. No monitor, migration, or legacy cleanup work was included.

## Final Bounded Fixes

- `AdminProcessEditor.save()` now returns `null` for client validation exits, matching its declared `Promise<ProcessApp | null>` contract.
- PASS: `npm.cmd run build`.
- PASS: the isolated high-value purchase Playwright scenario now selects deterministic `2026-08-01` through the Ant DatePicker popup. It verifies the exact payload, server 422 field error, retry with the same idempotency key, and navigation to requests.

## Task 11 Blocker Fixes

- New process-app submissions snapshot the applicant email. Detail retains `-` as the safe fallback for legacy snapshots without an email.
- Urge is shown only to the pending applicant and uses `PUT /requests/{id}/urge`; approvers who are not the applicant do not see the action.
- The UI now labels the snapshot view `已选择审批路径`. It displays approval/countersign nodes only and computes the active step from the actual pending node key, with a legacy node-index fallback. It does not claim a full condition-node trace.
- PASS: focused backend snapshot test and Ruff, frontend typecheck, and targeted detail/urge E2E tests.
