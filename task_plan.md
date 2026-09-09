Task ID: 20260907-autowsgr-decisive-debug-6e3a
Task Status: in_progress
Next Step: Review the stability/debug reports, fix post-combat WAITING_FOR_MAP and leave-confirm recognition, then rerun the remaining stability coverage.

# Task Plan: Decisive battle debug

## Goal
Use the isolated AutoWSGR worktree to investigate and fix the decisive-battle module while preserving the shared checkout.

## Worktree Binding
- Agent ID: 01a07c96-623e-7943-80a3-f73771818301
- Development branch: `codex/20260907-autowsgr-decisive-debug-6e3a`
- Development worktree: `C:\ShiinaKuroko\01.Project\AutoWSGR\.worktrees\20260907-autowsgr-decisive-debug-6e3a`

## Next Step
The user cleared the ship depot. Run 9 remaining tickets with periodic process/log checks; preserve prior logs and write a new report. The activity-page false-positive ROI remains a separate follow-up.

## Current Phase
Phase 4 - Testing & Verification (stability run)

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Identify constraints
- [x] Document in findings.md
- **Status:** completed

### Phase 2: Planning & Structure
- [x] Define staged visual-recognition approach
- [x] Confirm existing templates and state-machine entry points
- **Status:** completed

### Phase 3: Implementation
- [x] Execute the staged entry-recognition change
- [x] Add focused regression coverage
- [x] Fix decisive preparation return recognition and its stale map template path
- **Status:** completed

### Phase 4: Testing & Verification
- [x] Verify offline requirements and adjacent operation tests
- [x] Document test results
- [x] Run the four-case real-device recovery-chain after chapter 6 is reset
- [x] Verify decisive preparation return uses decisive-map recognition
- **Status:** completed

### Phase 5: Delivery
- [x] Review outputs
- [x] Deliver to user
- **Status:** completed

### Phase 6: Overnight Stability Run
- [x] Recover the refresh-state reset path; `refresh -> reset -> refreshed` passed during ticket 2.
- [x] Run the requested 9-ticket attempt with three leaves and one retreat per ticket; ticket 1 cleared and tickets 2-9 produced recorded errors/recoveries.
- [x] Collect expeditions during leave/recovery windows; 2 collections recorded.
- [x] Perform periodic process, ADB, and log health checks; no runner/device loss was observed.
- [x] Write stability and debug reports.
- **Status:** completed with failures documented

### Phase 7: Production Follow-up
- [ ] Fix post-combat `WAITING_FOR_MAP` recognition after result-page click.
- [ ] Fix or diagnose `confirm_exit` recognition during injected leave.
- [ ] Rerun stability coverage after the production fixes.
- **Status:** in progress

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Create a new local task branch from `ShiinaKuroko` | Existing debug worktrees belong to unrelated or completed tasks, and the current branch has advanced to `c5a464c`. |
| Place the worktree under `AutoWSGR/.worktrees` | The user explicitly requested the repository-owned path. |
| Preserve the shared checkout | It contains pre-existing user changes and must not be switched, cleaned, or overwritten. |

## Map Data Follow-up (2026-09-09)

- [x] Read the normal-map node contract and the supplied decisive route/enemy sources.
- [x] Add one normalized `silent_warrior/EX-*.yaml` file per Silent Warrior map with branch-qualified node IDs, directed `next` edges, reachable key points, and runtime enemy codes.
- [x] Add a data contract test and run the full `testing/ops` suite.
- [x] Integrate runtime loading, leftmost route selection, and branch-count ROI recognition without persisting a route column.
- [x] Remove the obsolete `enemy_spec.yaml` data source.

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Initial planning patch did not match the generated UTF-8 BOM template | Read the generated files and recreated only the new task-scoped planning files with the required task header. |
