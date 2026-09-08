# Findings & Decisions

## Requirements
- Create an isolated AutoWSGR worktree under `AutoWSGR/.worktrees`.
- Base it on the committed `ShiinaKuroko` branch.
- Keep the worktree available for subsequent decisive-battle debugging.
- Do not alter the shared checkout or unrelated existing worktrees.

## Research Findings
- The coordination repository is `C:/ShiinaKuroko/01.Project`.
- The target backend repository is `C:/ShiinaKuroko/01.Project/AutoWSGR`.
- The shared checkout is on `ShiinaKuroko` with pre-existing user changes; its committed tip is `c5a464c7719bea74a7a26079b9656644237ff8cb`.
- Existing `c4d8` and `9c2e` worktrees are respectively an in-progress repair-method task and a completed enemy-rule task, so neither matches this new decisive-battle task.
- The new worktree is clean apart from task-scoped planning files.
- The worktree is bound to the current Agent identity.
- The repository contains a dedicated decisive-battle UI E2E module at `testing/ui/decisive_battle_page/e2e.py`, a shared runner at `testing/ui/run_all_e2e.py` and `testing/ui/run_all_e2e.ps1`, plus focused unit/operation tests under `testing/ops/test_decisive_unit.py` and `testing/ops/decisive_battle.py`.
- `examples/decisive.py` is the user-facing decisive-battle example and may be a safer static entry point than the UI E2E runner until its device requirements are confirmed.
- The requested complete tool exists only in the old `20260830-autowsgr-upgrade` worktree as the tracked `tools/e2e/` package (`run.py`, `framework.py`, and cases); the current `ShiinaKuroko`-based worktree does not contain that package.
- The old worktree has unrelated uncommitted migration changes and a separate uncommitted edit to `tools/e2e/cases/bath_repair.py`; only the committed `tools/e2e/` source should be considered for transfer.
- The committed `tools/e2e/` package was restored into the bound worktree, its framework was adapted to the current `autowsgr.scheduler`, `autowsgr.context`, `autowsgr.infra`, and `autowsgr.ui` APIs, and a current-architecture `decisive` case was added.
- The E2E argument splitter originally rejected the documented `screenshot --no-launch` form; it now accepts global flags before or after the case name.
- The copied framework originally called `Launcher.disconnect()`, which does not exist in the current launcher; cleanup now disconnects `launcher.ctrl` and avoids reporting a failure when connection never completed.
- The read-only screenshot E2E passed on `127.0.0.1:16384`: device connected at 1280x720, screenshot succeeded, page recognition returned `主页面`, and cleanup completed with exit code 0.
- The first real decisive run used the current `usersettings.yaml` (chapter 1, one round) and reached the decisive overview, reset the chapter, entered the map, then timed out after 8 seconds waiting for `fleet_acquisition` during `CHOOSE_FLEET`; the controller returned `ERROR`.
- The decisive E2E cleanup returned to the main page and disconnected the device. The only transport warning was scrcpy `WinError 10038` during socket shutdown.
- The GUI source file `AutoWSGR-GUI/resource/system_daily_plans/decisive-决战第6章.yaml` defines chapter 6, one round, quick repair enabled, level1 `[U-47, U-1405, U-1206, U-2540, U-81, U-96]`, and a 21-entry level2 list.
- The GUI plan contract has no flagship-priority, repair-level, full-destroy, or useful-skill fields; the backend default file now uses the GUI values for shared fields and retains its existing backend-only values for those fields.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| `codex/20260907-autowsgr-decisive-debug-6e3a` | Unique local task branch for this debug effort. |
| `C:/ShiinaKuroko/01.Project/AutoWSGR/.worktrees/20260907-autowsgr-decisive-debug-6e3a` | Repository-owned worktree path requested by the user. |
| Use `c5a464c` as the base | It is the current committed `ShiinaKuroko` tip. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Shared checkout contains many user deletions and untracked debug/planning data | Left the shared checkout untouched and created the worktree from its committed branch tip. |
| The planning initializer writes a UTF-8 BOM | Recreated the generated files with the required task header using the direct edit tool. |
| One parallel read used a nonexistent old worktree path | Recorded the path error and reran inspection against the bound worktree path. |
| Direct system Python lacked locked dependencies | Ran `uv sync --all-groups` in the bound worktree. |
| The first E2E import probe had a PowerShell quoting error | Reran the import probe through a PowerShell here-string; imports passed. |
| Documented E2E flag order was rejected | Fixed `tools/e2e/run.py` argument splitting and added a direct assertion check. |
| Current launcher has no `disconnect()` method | Fixed the copied framework to disconnect `launcher.ctrl` and verified the screenshot E2E. |
| Decisive run timed out waiting for `fleet_acquisition` | Stopped further real-device runs and recorded the failure; wait for the user's configuration before rerunning. |

## Configuration Source
- Source: `C:/ShiinaKuroko/01.Project/AutoWSGR-GUI/resource/system_daily_plans/decisive-决战第6章.yaml` (read-only).
- Applied to: `usersettings.yaml` in the bound AutoWSGR decisive-debug worktree.

## Resources
- `C:/ShiinaKuroko/01.Project/AGENTS.md`
- `C:/ShiinaKuroko/01.Project/AutoWSGR/AGENTS.md`
- `C:/Users/mzhia/.codex/skills/planning-with-files/SKILL.md`

## Recognition Fix
- Additional fallback requirement: `CHOOSE_FLEET` must not be trusted solely from the state enum. Before OCR or any fleet click, the current screen must positively match the fleet-acquisition button/template; otherwise the controller must re-detect the current phase and route without assuming first-entry, retreat, or leave-resume state.
- The existing OpenCV template check is present in `wait_for_fleet_overlay_stable()`, but its current timeout path raises directly instead of re-routing from a fresh phase detection. `_has_chosen_fleet` is also set before that validation and should move after successful fleet-page completion.
- The new recovery-chain E2E contract has four cases: initial advance choice and normal fleet selection followed by retreat; retreat re-entry with mocked empty fleet selection followed by retreat; retreat re-entry with normal formation followed by leave; and leave resume with no advance choice, stopping on preparation without starting battle.
- The recovery-chain mock is tool-only and is removed from production logic; it returns empty fleet options/one-fleet sufficiency only in case 2.
- Correction: the `_use_last_fleet_attempts` hypothesis was rejected for this user case; it is an in-task retreat/leave path, not a new task resuming through the “use last fleet” entry.
- The clarified three-path contract is now explicit: first entry may show advance choice, same-task retreat re-entry may show it again, and leave/resume at an already selected point may show no choice.
- After an advance choice is confirmed, the controller returns to `WAITING_FOR_MAP` and lets fresh visual recognition choose `CHOOSE_FLEET` or `PREPARE_COMBAT`; it no longer hardcodes the next phase.
- The user-provided debug log is the actual chapter-6 case: after the first stage-1 entry and retreat, the second entry at `00:15:17` again logged `选择前进点` and then waited for `fleet_acquisition` until timeout.
- Earlier `_use_last_fleet_attempts` recovery was considered but rejected for this same-task retreat/leave path; the current fix relies on fresh visual entry recognition instead.
- The decisive code already has a positive `ADVANCE_CHOICE` template match at `autowsgr/image_resources/pages/decisive.py` and overlay detection at `autowsgr/ui/decisive/overlay.py`; `DecisiveMapController.detect_decisive_phase()` checks this overlay before classifying the map page.
- The unsafe behavior was at the state/action boundary: entry used a fixed 2-second delay, and `select_advance_card()` clicked coordinates without rechecking that the choice overlay was visible.
- The fix removes the fixed delay, stages positive `USE_LAST_FLEET` and `ADVANCE_CHOICE` checks before the map-page fallback, routes a confirmed map page directly to `PREPARE_COMBAT`, and gates advance-card clicks on a positive `ADVANCE_CHOICE` template match.
- The no-popup paths do not call `select_advance_card()`: only a positive `ADVANCE_CHOICE` overlay result enters `DecisivePhase.ADVANCE_CHOICE`; resume/terminal paths route to `PREPARE_COMBAT` or `STAGE_CLEAR`.
- The current backend decisive data has `map_end`, `key_points`, and `enemy`, but no per-node `next` route graph. GUI map data covers normal/event maps, not decisive routes, so route-specific expectations cannot be inferred from the current repository.
- The first mock E2E case design was invalid: it reused the normal entry path and reached `使用上次舰队` before the insufficient-fleet injection, so it did not isolate the requested same-task retreat/re-entry chain. The mock flag was removed without changing production code.
- The captured chapter-6 log proves the advance card was not clicked blindly: `00:34:12.559` detected `advance_choice`, `00:34:12.609` entered `ADVANCE_CHOICE`, then `00:34:12.612` clicked the card and `00:34:13.126` clicked confirm.
- The earlier chapter-1 failure was a different bug: at `00:21:30.224`, missing ship-marker recognition caused the old fallback to force `PREPARE_COMBAT → CHOOSE_FLEET`, which later timed out waiting for `fleet_acquisition`; it did not click an unrecognized advance popup.

## Tomorrow: Event Page False Positive
- `BaseEventPage.is_current_page()` first checks the generic `event/fight_button_20260730_540p.png` at confidence `0.8`.
- On the decisive formation screenshot `logs/e2e_tools/decisive/20260908_034922/images/NavError_034216_477.png`, that matcher returned confidence `0.869940996170044` at normalized center `(0.130078125, 0.050694444444444445)`, which is the top-left back button, not an event attack button.
- Difficulty-icon and event-title checks were both `None`; the false hit won because `EVENT_MAP` is registered before other page candidates.
- Narrow fix for tomorrow: constrain the event fight-button matcher to the real bottom-right activity-button ROI and add an offline regression using this screenshot. Do not change decisive reset or combat logic for this issue.

## Formation Back-Return Root Cause
- The latest `BATTLE_PREP -> MAP` timeout occurs after the back click succeeds; failure screenshots are already on the decisive map.
- `BattlePreparationPage.go_back()` waits for generic `PageName.MAP`, whose tabbed-map checker does not recognize the decisive map layout.
- `DecisiveMapController.is_decisive_map_page()` does recognize that screen, but it is not the checker used by the preparation-page return path.
- The event false positive is a secondary first-frame misclassification; after it disappears, the generic MAP target still returns `None` and causes the timeout.

## Decisive Preparation Return Fix
- `DecisiveBattlePreparationPage` is the concrete page used by decisive fleet scanning and fleet changes.
- Its inherited `BattlePreparationPage.go_back()` waited for generic `MapPage.is_current_page()`, which does not recognize the decisive map layout.
- Added a decisive-only `go_back()` override using `is_decisive_map_page`; generic campaign/exercise preparation navigation remains unchanged.
- The first rerun still timed out because `is_decisive_map_page()` itself used the stale `decisive_map_540p.png` template; the actual return screenshot scored `0.2687` against the `0.85` threshold.
- The existing `SIG_MAP_PAGE` pixel signature matched that same screenshot 5/5, so `is_decisive_map_page()` now uses `PixelChecker.check_signature` without adding a new asset.
- Offline verification after the final fix: `uv run pytest -q testing/ops` -> `115 passed`; compileall and selected pre-commit hooks passed.
- Final recovery-chain verification passed all 44 steps, including Case 3 map return/temporary leave and Case 4 resume stopping before battle.
