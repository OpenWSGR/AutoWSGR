Task ID: 20260907-autowsgr-decisive-debug-6e3a
Task Status: done
Next Step: Activity-page false-positive ROI remains a separate follow-up.

# Task Plan: Decisive battle debug

## Goal
Use the isolated AutoWSGR worktree to investigate and fix the decisive-battle module while preserving the shared checkout.

## Worktree Binding
- Agent ID: 01a07c96-623e-7943-80a3-f73771818301
- Development branch: `codex/20260907-autowsgr-decisive-debug-6e3a`
- Development worktree: `C:\ShiinaKuroko\01.Project\AutoWSGR\.worktrees\20260907-autowsgr-decisive-debug-6e3a`

## Next Step
Activity-page false-positive ROI remains a separate follow-up.

## Current Phase
Phase 4 - Testing & Verification

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

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Create a new local task branch from `ShiinaKuroko` | Existing debug worktrees belong to unrelated or completed tasks, and the current branch has advanced to `c5a464c`. |
| Place the worktree under `AutoWSGR/.worktrees` | The user explicitly requested the repository-owned path. |
| Preserve the shared checkout | It contains pre-existing user changes and must not be switched, cleaned, or overwritten. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Initial planning patch did not match the generated UTF-8 BOM template | Read the generated files and recreated only the new task-scoped planning files with the required task header. |
