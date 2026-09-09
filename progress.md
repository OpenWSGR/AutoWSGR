# Progress Log

Task ID: 20260907-autowsgr-decisive-debug-6e3a
Task Status: in_progress
Next Step: Run the remaining 9 tickets with 15-minute health checks and stop after the ticket count completes.

### 2026-09-09 04:30: refresh-state reset recovery
- Diagnosed the stability-run loop: `reset_chapter()` only searched the `reset_button.png` ROI, while the real `refresh` overview presents the existing `entry_refresh_540p.png` as a large bottom-center `重置关卡` button.
- Added `RESET_ENTRY_ROI` and a staged `ENTRY_REFRESH` fallback in `autowsgr/ui/decisive/battle_page.py`; the original right-side `RESET_BUTTON_ROI` path remains first.
- Added `test_reset_chapter_falls_back_to_refresh_entry` to `testing/ops/test_decisive_unit.py`.
- Offline reset tests: `3 passed`.
- Real-device smoke: `BEFORE refresh` → `识别到重置入口: entry_refresh` → `confirm_1` → `AFTER refreshed`; no ticket was started.
- First stability run: ticket 1 completed all three stages with 3 leaves and 1 retreat; ticket 2 hit a stale fleet-overlay/state-machine timeout at `05:09:28`, then the old harness restarted home without resetting the chapter and contaminated later tickets. The run was stopped at `05:14`.
- Added harness recovery: restart home → re-enter Ex-6 → reset `challenging/refresh` → verify `refreshed`; stop if recovery verification fails.
- Added production stale-frame guard: `fleet_acquisition` must match again on a fresh screenshot before entering OCR; added an offline regression.
- Added start-of-run chapter reset: the harness now verifies `refreshed` before ticket 1, covering an interrupted prior process.
- Final run: ticket 1 completed; ticket 2 hit a `WAITING_FOR_MAP` timeout and reset recovery recognized `reset_button` but did not open `confirm_1`, so the run was stopped safely. Added immediate report/exit when recovery is halted instead of waiting for the deadline-only expedition loop.
- Reports written: `logs/e2e_tools/decisive_stability/20260909_053232/stability_report.md` and `debug_report.md`.
- User reports the ship depot has been cleared and authorizes resuming the remaining 9-ticket stability run.
- Added `--stop-after-tickets` so the run exits immediately after the requested count instead of waiting for the next day's 08:00.

### 2026-09-08: decisive preparation return checker
- Confirmed the prior real-device timeout was after a successful back click; the screenshot was already the decisive map.
- Added `DecisiveBattlePreparationPage.go_back()` using `is_decisive_map_page` instead of the generic tabbed-map checker.
- Added a focused regression asserting the decisive checker is passed to `click_and_wait_for_page`.
- Verification: focused decisive tests `12 passed`; full `testing/ops` `114 passed`; compileall passed; selected pre-commit passed.
- Next: rerun the existing four-case real-device recovery chain and inspect whether Case 3 reaches temporary leave and Case 4.

### 2026-09-08 22:17: first rerun after decisive go_back override
- Case 1, Case 2, and Case 3 formation completed.
- Case 3 `编队完成回到地图` still timed out; the back click had already returned to the decisive map.
- Offline matching of the failure screenshot showed `decisive_map_540p.png` confidence `0.2687`, below the `0.85` threshold.

### 2026-09-08: final decisive map recognition fix
- Replaced the stale template check inside `is_decisive_map_page()` with the existing `SIG_MAP_PAGE` pixel signature.
- Added positive/negative unit coverage for the map signature.
- Verification: focused decisive tests `13 passed`; full `testing/ops` `115 passed`; compileall and selected pre-commit passed.

### 2026-09-08 22:27: final real-device recovery-chain
- Automatic reset, Case 1 retreat, Case 2 mocked one-ship retreat, Case 3 formation/return/temporary leave, and Case 4 resume all passed.
- Result: `44 steps, 0 failures`; Case 4 stopped on the preparation page without calling `start_battle`.
- E2E log directory: `logs/e2e_tools/decisive/20260908_222708`.

### 2026-09-08 22:35: committed-version real-device recovery-chain
- Re-ran the same four-case chain from the committed code checkpoint `78b77de`.
- Result: `44 steps, 0 failures`; Case 3 map return/temporary leave and Case 4 resume passed again.
- Case 4 ended on the preparation page without starting battle; cleanup returned the device to the main page.
- E2E log directory: `logs/e2e_tools/decisive/20260908_223501`.
- Code checkpoint: `78b77de` (`fix(decisive): recognize map after preparation return`).

## Session: 2026-09-08

### Current Status
- **Phase:** 1 - Requirements & Discovery
- **Started:** 2026-09-08

### Actions Taken
- Confirmed the coordination root and the independent AutoWSGR repository root.
- Read the parent and AutoWSGR repository instructions.
- Preserved the shared `ShiinaKuroko` checkout and its existing user changes.
- Created `C:\ShiinaKuroko\01.Project\AutoWSGR\.worktrees\20260907-autowsgr-decisive-debug-6e3a` from `ShiinaKuroko`.
- Created branch `codex/20260907-autowsgr-decisive-debug-6e3a` at `c5a464c`.
- Bound the worktree to the current Agent identity and initialized task-scoped planning files.
- The first template patch did not match the generated file and made no changes; the generated files were reread before recreating them.
- Restored the committed `tools/e2e` package from `codex/20260830-autowsgr-upgrade` without touching that dirty source worktree.
- Adapted the E2E framework to the current launcher/context/UI APIs and added `tools/e2e/cases/decisive.py`.
- Fixed global E2E flag parsing so the documented `screenshot --no-launch` invocation works.
- Ran `uv sync --all-groups` to install the repository lockfile environment.
- Read the GUI system plan `AutoWSGR-GUI/resource/system_daily_plans/decisive-决战第6章.yaml` without modifying the GUI repository.
- Applied its chapter-6 shared fields to `usersettings.yaml`: one round, quick repair enabled, the six level1 ships, and the full level2 list.
- Retained the backend-only flagship priority, repair level, full-destroy, and useful-skill settings because the GUI source contract does not define them.
- Started one real-device chapter-6 E2E with the imported default configuration, then stopped it at the user's request.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| `git rev-parse --show-toplevel` | AutoWSGR task worktree root | `C:/ShiinaKuroko/01.Project/AutoWSGR/.worktrees/20260907-autowsgr-decisive-debug-6e3a` | Pass |
| `git branch --show-current` | New decisive debug branch | `codex/20260907-autowsgr-decisive-debug-6e3a` | Pass |
| `git rev-parse HEAD` | Current `ShiinaKuroko` base | `c5a464c7719bea74a7a26079b9656644237ff8cb` | Pass |
| Agent binding verification | Current Agent owns the worktree | Binding verified | Pass |
| `uv run pytest -q testing/ops/test_decisive_unit.py` | Existing decisive unit regression remains green | `1 passed` | Pass |
| `uv run python tools/e2e/run.py --list` | Copied tool discovers cases | `decisive` and existing cases listed | Pass |
| `uv run python tools/e2e/run.py --serial 127.0.0.1:16384 screenshot --no-launch` | Device/screenshot/page-recognition chain works | Connected at 1280x720, recognized `主页面`, exit 0 | Pass |
| `uv run python tools/e2e/run.py --serial 127.0.0.1:16384 --with-ocr decisive --times 1` | One real decisive round completes | Reached `CHOOSE_FLEET`, timed out waiting for `fleet_acquisition`, result `ERROR`, exit 1 | Root-cause evidence |
| GUI plan to backend config mapping | Shared fields are valid for `DecisiveConfig` | Applied to `usersettings.yaml`; no device run after the config update | Pass |
| Offline GUI-to-backend content comparison | Select the GUI system plan whose YAML chapter is 6 and compare shared fields | `chapter=6`, `rounds=1`, `level1=6`, `level2=21`, quick repair enabled | Pass |
| Chapter-6 real-device E2E | Reach and observe the configured decisive path | Passed fleet acquisition OCR and selected `U-1405` plus `鹦鹉螺`; reached stage 1 node A preparation before user interruption | Interrupted |

### Errors
| Error | Resolution |
|-------|------------|
| Initial planning patch did not match the generated UTF-8 BOM template | Reread the generated files and recreated only the task-scoped planning files; no source files were involved. |
| Direct system Python lacked project dependencies | Installed the locked environment with `uv sync --all-groups`. |
| First screenshot command put `--no-launch` after the case and was rejected | Fixed the argument splitter, then reran the documented command successfully. |
| Cleanup called missing `Launcher.disconnect()` | Changed cleanup to disconnect `launcher.ctrl`; screenshot E2E then passed. |
| Decisive E2E timed out on `fleet_acquisition` | Stopped further device runs pending the user's configuration. |
| First offline comparison selected the first decisive YAML glob result (chapter 1) | Selected the source by parsed `chapter == 6` and reran the comparison successfully. |
| User interrupted the chapter-6 E2E before final result/cleanup | Stopped all further device actions; final result and cleanup state remain unverified. |

### Recognition-gated entry fix
- Added the tools E2E `recovery-chain` scenario implementing the four requested cases; the last case verifies preparation-page readiness without calling `start_battle`.
- Applied the clarified three-path flow: first entry and same-task retreat can recognize `ADVANCE_CHOICE`; leave/resume can proceed without it.
- After card confirmation, route through fresh phase recognition instead of forcing `CHOOSE_FLEET`.
- Read the actual chapter-6 log: the first run bought a fleet, found insufficient state, retreated, and the interrupted/restarted path lacked a current-fleet scan.
- The attempted `_use_last_fleet_attempts` fallback was reverted after the user clarified this is an in-task retreat/leave path, not a task restart through the “use last fleet” entry.
- Removed the post-entry fixed delay in `autowsgr/ops/decisive/handlers.py`.
- Replaced the old ship-icon/no-overlay guess with staged recognition: wait for `USE_LAST_FLEET`, then `ADVANCE_CHOICE`, then accept only a positive fleet overlay or map-page match; a confirmed map page routes directly to `PREPARE_COMBAT`.
- Added an `ADVANCE_CHOICE` recognition gate inside `select_advance_card()`.
- Updated `testing/ops/test_decisive_unit.py` with no-delay, no-premature-fallback, and click-gating checks.

| `uv run pytest -q testing/ops/test_decisive_unit.py` | Verify recognition-gated entry, clicks, and post-choice routing | `4 passed` | Pass |
| `uv run python -m compileall -q autowsgr/ops/decisive autowsgr/ui/decisive testing/ops/test_decisive_unit.py` | Compile changed modules | Exit 0 | Pass |
| `git diff --check` | No whitespace errors | Exit 0 | Pass |
| `uv run python -m compileall -q tools/e2e` | Compile the recovery-chain E2E case | Exit 0 | Pass |
| `uv run python tools/e2e/run.py --list` | Discover the updated E2E package | `decisive` listed | Pass |

### Map-condition clarification
- Confirmed the advance-card gate is reached only from `DecisivePhase.ADVANCE_CHOICE`, which is set by positive overlay recognition.
- Confirmed terminal nodes route through `MapData.is_stage_end()` to `STAGE_CLEAR`; resume/no-popup paths do not invoke `select_advance_card()`.
- Confirmed the repository does not currently contain decisive per-node route edges (`next`); do not invent a mapdata condition until the actual route source is available.
- Read the captured logs for the interrupted chapter-6 run and the earlier chapter-1 failure. The chapter-6 advance click followed a positive overlay recognition; the real historical failure was the old no-ship-marker fallback to `CHOOSE_FLEET`.

### Fleet-page fallback requirement
- Record the next safety boundary: validate the fleet-acquisition template before OCR/clicks, re-detect and route when it is absent, and only mark `_has_chosen_fleet` after successful completion.
- No production change or device run performed for this requirement yet.
- Started the first mock insufficient-fleet E2E, then stopped it when the case design was found to enter through `使用上次舰队` instead of isolating the requested same-task retreat/re-entry path.
- Removed the flawed mock flag; no production code was changed by that attempt.

### Staged entry recognition completion
- Initialized `_skip_advance_choice` in `DecisiveBase` so post-card recognition is valid for every controller instance.
- Fixed the unrecognized-use-last-fleet unit test to advance its mocked monotonic clock past the polling deadline.
- Added the same state field to the delayed-entry test context.
- First rerun failed because that context also lacked `_use_last_fleet_attempts`; added the existing state field to the fixture.
- Second rerun exposed a stale mock setup still targeting `detect_decisive_phase`; configured the new `wait_for_entry_phase` return value instead.
- Review found the handler was checking the pre-poll screenshot after staged recognition; moved the screenshot after the poll and added an assertion for the staged-recognition call.
- Direct `uv run ruff check ...` could not start because `ruff` is not in the locked runtime environment; the repository pre-commit hook supplied ruff and passed after fixing 5 import/format issues.
- Removed the legacy ship-icon gate from the final map-page fallback: positive map-page recognition now routes directly to `PREPARE_COMBAT`, matching the requested formation fallback without assuming fresh entry or resume state.
- Added an offline regression test for the staged order: `USE_LAST_FLEET` -> `ADVANCE_CHOICE` -> confirmed map-page fallback.

### Final offline verification
- `uv run pytest -q testing/ops`: `102 passed`.
- `uv run python -m compileall -q autowsgr/ops/decisive autowsgr/ui/decisive testing/ops/test_decisive_unit.py tools/e2e`: passed.
- `uv run pre-commit run --files ...`: all selected hooks passed.
- `git diff --check`: passed.
- No real-device run was started after this implementation; the recovery-chain E2E remains pending the user's chapter-6 reset.

### Real-device case preflight
- Reviewed `tools/e2e/cases/decisive.py` before starting hardware actions.
- Found the recovery-chain case expected `ADVANCE_CHOICE` immediately after map entry and did not handle the valid recognized `USE_LAST_FLEET` step after a chapter reset.
- The case needs an optional positive `USE_LAST_FLEET` route before its `ADVANCE_CHOICE` assertion; production code is unchanged for this tool-only correction.
- Initial tool pre-commit then reported the case's pre-existing complexity plus three nested-if warnings; added the established single-E2E complexity noqa and combined those conditionals.

### Real-device attempt 2026-09-08 02:31
- Device `127.0.0.1:16384` connected at 1280x720 and chapter 6 overview navigation passed.
- Case 1 passed `USE_LAST_FLEET` positive recognition/click, confirmation, `ADVANCE_CHOICE` positive recognition, and advance-card/confirm clicks.
- Case 1 then failed while waiting for the post-card state with `决战入口页面未识别到预期弹窗或地图页`.
- The retained `NavError_023142_320.png` and `NavError_023155_202.png` screenshots show the actual screen is the `战备舰队获取` overlay, so the failure is an offline template/threshold or entry-poll recognition issue, not a blind advance click.
- The E2E framework recovered by restarting the game and disconnected the device; no battle was started.
- Offline matching against the retained screenshot gave `decisive_fleet_acq=0.7427`, below the old `0.85` threshold; narrowed the fleet-overlay threshold to `0.70` while preserving `0.85` for other decisive templates.
- Made recovery-chain Case 1 reset chapter 6 explicitly after reaching the overview, so a failed prior attempt cannot contaminate the next fresh-entry case.

### Real-device attempt 2026-09-08 02:38
- The second run connected successfully, but the previous failed run had left the game in the fleet-acquisition page; `reset_chapter()` was invoked against that page and timed out without a confirmation dialog.
- User confirmed the device was visibly stuck on the `战备舰队获取` page. No further clicks were issued after this confirmation; the runner's cleanup/restart path was allowed to finish.
- This proves the recovery-chain runner needs an explicit precondition/recovery step that verifies the decisive overview before resetting, rather than assuming a prior failed run left the overview usable.

### User reset confirmation
- User confirmed chapter 6 and the device state were reset after the contaminated second attempt; safe to retry the recovery-chain.

### Real-device attempt 2026-09-08 02:44 (user stopped)
- Third run connected and reached the decisive overview, then entered the explicit Case 1 reset action.
- User requested an immediate stop while the runner was in its recovery path; no `python`/`uv` E2E process remains.
- The four-case chain was not reached in this run. No further device actions should be taken until the user gives a new instruction.

### OCR tool inventory
- The current worktree already contains the compatible OCR tools `tools/ocr_crop_tool.py` and `tools/ocr_change_fleet_e2e/`.
- The same-named files in `20260830-autowsgr-upgrade` use the separate `autowsgr.application.*` architecture and must not be copied into this branch.

### Fixed last-fleet ROI recognition
- Added the 720p normalized ROI from the user's red-box screenshot: `x=0.82..1.00`, `y=0.30..0.50`.
- The entry stage now waits 3 seconds, performs three immediate ROI template checks, and downgrades to `ADVANCE_CHOICE` after three misses.
- The actual click path uses the same ROI so recognition and clicking share one coordinate boundary.
- First ROI test rerun exposed a stale fixture that did not mock the new helper; added the helper mock before rerunning.
- Second ROI test rerun exposed the same test's stale assertion for the removed generic use-last call; narrowed it to the remaining advance-choice stage.

### Fixed ROI verification
- `uv run pytest -q testing/ops`: `103 passed`.
- Selected pre-commit hooks, compileall, and `git diff --check` passed.
- No real-device run was started for this ROI change; the user's screenshot supplied the 720p coordinate basis.

### User authorized ROI real-device run
- User requested rerunning the original four-case recovery-chain with the fixed-ROI implementation.
- User then authorized automatic chapter reset for this run.
- Updated Case 2's mock to click the first real card in the game while bypassing OCR, close the overlay, retain exactly one ship in state, and let the mocked node-A fleet check trigger retreat.

### Real-device attempt 2026-09-08 03:10
- Automatic reset did issue the reset-coordinate click, but the screenshot at timeout showed the decisive map with `A1/A2` `ADVANCE_CHOICE`, not the chapter-overview reset confirmation.
- Therefore the click landed on the advance-choice confirm area; `confirm_operation()` was waiting for the wrong dialog. The real defect is a missing overview-page precondition before `reset_chapter()`, not a missing generic confirm template.
- The run stopped before Case 1; no further device action was issued after this evidence.

### Reset-entry recognition fix
- Added the user-provided `reset_button.png` as a 1280x720 decisive template.
- `reset_chapter()` now waits for a positive reset-button match and clicks its match center before invoking the existing generic confirmation recognition.
- Added an offline regression test proving the reset coordinate is never used when the reset button is not recognized.
- Refined reset recognition to the screenshot ROI `x=0.64..0.73`, `y=0.84..1.00` before matching, then click the matched center.
- Confirmed the existing entry state machine semantics with a regression: `REFRESH` resets, re-detects `REFRESHED`, then enters the map.

### User authorized reset-ROI real-device run
- User confirmed the game is currently on the home page and chapter 6 is not reset; run the recovery-chain with automatic reset-button ROI recognition.

### Real-device attempt 2026-09-08 03:38
- Reset ROI and confirmation passed; Case 1 and Case 2 completed successfully, including a real first-card click in the Case 2 mock and normal retreat handling.
- Case 3 reached normal fleet selection and the formation page, but the E2E case hard-coded unavailable `U-47`; OCR had purchased `鹦鹉螺` and `M-296`.
- Changed Case 3 to use the actual ships recorded in the current run for formation; production code was not changed by this correction.

### Real-device attempt 2026-09-08 21:51
- Automatic reset, Case 1, and Case 2 passed again.
- Case 3 passed advance recognition, normal purchase, formation-title guard, and actual formation completion.
- Case 3 still failed only at returning from preparation to the map; Case 4 was not reached. This remains the pending event/page-recognition issue.

### Real-device attempt 2026-09-08 21:51 repeat
- Automatic reset, Case 1, Case 2, Case 3 formation entry, formation-title guard, and actual formation completion passed again.
- After the preparation-page back click, `BATTLE_PREP -> MAP` recognition timed out; no temporary-leave action or Case 4 action was reached.
- This reproduces the same page-recognition boundary independently of formation entry and fleet OCR.

### Real-device attempt 2026-09-08 03:41
- The run stopped before decisive navigation: an event-map stage-card overlay repeatedly blocked `定位决战总览页` and the framework timed out returning to the main page.
- No reset click or decisive case action occurred in this run; no further device recovery clicks were issued.
- User confirmed the actual device is currently on the fleet-formation page despite the framework cleanup summary; preserve this page and do not auto-navigate.
- Latest screenshots and logs show this run did not click formation: the page was already `出征准备`, while the framework misrecognized it as `活动页面 (score=0.870)` and repeatedly clicked the event close coordinate. The formation entry came from the previous Case 3 run, whose failed cleanup falsely reported returning home.

### Real-device attempt 2026-09-08 21:45
- Automatic reset ROI and confirmation passed.
- Case 1 and Case 2 passed completely; Case 2 physically clicked the first fleet card before the insufficient-fleet retreat check.
- Case 3 passed advance recognition, normal fleet acquisition, formation entry, and formation completion using the actual purchased `M-296` and `鹦鹉螺`.
- Case 3 failed only while returning from formation to the map, reproducing the known `EVENT_MAP` false-positive page-recognition issue; Case 4 was not reached.

### Tomorrow handoff
- Production event-page recognition still needs the bottom-right fight-button ROI fix described in `findings.md`.
- Do not resume real-device recovery-chain until that false-positive fix is tested offline.

### Decisive formation title guard
- Added `fleet_name.png` as a 1280x720 OpenCV template with ROI `x=0.08..0.26`, `y=0.11..0.22`.
- `enter_formation()` now requires three title checks; on failure it returns to the map and retries formation once before raising.
- Verification: focused decisive tests `11 passed`; full `testing/ops` `113 passed`; selected pre-commit and compile checks passed.

### Formation back-return diagnosis
- The back click succeeds and the screenshot is already the decisive map.
- The wait path targets generic `PageName.MAP`, while decisive-map recognition lives only in `DecisiveMapController.is_decisive_map_page()`; this is the primary return timeout cause.
- Event-page false matching affects the first recognition frame but is secondary to the wrong target checker.

### Commit checkpoint
- Code/E2E/config checkpoint committed as `5c2eb12` (`fix(decisive): gate entry and reset actions by recognition`).

### Baseline synchronization
- Rebased the task branch onto `origin/ShiinaKuroko@9b000b4` without conflicts.
- Rebased code checkpoint: `70517d1`; rebased planning checkpoint: `e927739`.
- Post-rebase verification: `uv run pytest -q testing/ops` -> `111 passed`; compileall, selected pre-commit hooks, and diff check passed.

### Event-page false-positive diagnosis
- `BaseEventPage.is_current_page()` checks the generic `fight_button_20260730_540p.png` first at confidence `0.8`.
- On the decisive formation screenshot, that full-screen match falsely hits the top-left back button at confidence `0.86994`; difficulty-icon and event-title checks were not involved.
- Because `EVENT_MAP` is registered before `DECISIVE_BATTLE`/other page candidates, the false event hit wins page recognition. The minimal fix boundary is an event-fight-button bottom-right ROI (the real event button location), not a reset or decisive-flow change.

### 2026-09-09: map data cross-check

- Read the normal-map YAML contract and the supplied decisive forward/enemy YAMLs.
- Built a read-only normalized preview: 18 maps, 319 nodes, 401 edges; all terminal labels match legacy `map_end`.
- First structural probe used the legacy enemy shape as a mapping and failed because `enemy_spec.yaml` stores `enemy` as a padded list; reran with shape-aware parsing.
- One inspection probe referenced a non-existent `autowsgr/types/decisive.py`; the enum is defined in `autowsgr/types.py`. No repository files were changed by either failed read.

### 2026-09-09: normalized decisive map archive

- Generated 18 `autowsgr/data/map/decisive_battle/silent_warrior/EX-*.yaml` files from the supplied forward graph and enemy formations, using branch-qualified node IDs and normal-map `next` semantics.
- Removed the temporary combined archive and normalized enemy formations through `ShipType` member names, with `AF` retained for the special `机场` unit. New map data stores only actual enemy codes; it does not copy the legacy index-0 sentinel.
- Corrected the two legacy decisive aliases after validation: `CBG -> BG` for `大巡` and `BG -> BBG` for `导战`.
- The first conversion assertion assumed every source formation had six units; the source contains 1-6 actual units. The new archive preserves those lengths instead of padding them.
- The data test first rejected legacy empty padding, then caught the incompatible `CBG` code; both issues were corrected without weakening unknown-code validation.

### 2026-09-09: route data runtime integration

- Replaced `MapData`'s static `map_end`/`key_points` and legacy `enemy_spec.yaml` loader with per-EX `silent_warrior` map loading.
- Added leftmost-route successor queries; no column or route cursor is persisted.
- Added the three-card ROI from `adb-teamchose3.png`; unknown recovery state checks both two-card and three-card ROIs, while known route state selects the matching ROI.
- Removed `get_advance_choice()`'s unconditional index-0 decision; the handler now always clicks the leftmost card after route-derived recognition.
- Deleted `autowsgr/data/map/decisive_battle/enemy_spec.yaml` after removing all Python references.
- Three-card ROI is `x=142..429, y=235..431` at 1280x720, taken from `adb-teamchose3.png`; the existing two-card ROI remains unchanged.
- The first integration pre-commit caught a `TypeError` lint and a missing ROI return annotation; both were fixed and the second run passed.
- The first data test exposed unreachable legacy key points; filtered each map's key points to its actual node labels and recorded the mismatch without changing `enemy_spec.yaml`.
- Data contract test: `uv run pytest -q testing/ops/test_decisive_map_data.py` -> `1 passed`.
- File-scoped pre-commit (including Ruff, YAML/file checks, and codespell) passed.
- The first generation attempt used the wrong legacy-data path and failed before writing; the corrected generation completed with 18 maps, 319 nodes, and 401 edges.

### Stability run attempt 2026-09-09 08:24

- Started the requested 9-ticket run with `--stop-after-tickets` and seed `314859790`.
- The stale `ADVANCE_CHOICE` screen was recovered by the normal startup path: page recognition failed, then the game was force-restarted to the home page.
- Ex-6 navigation and `challenging` entry recognition passed.
- `reset_button.png` was recognized twice at `(0.684, 0.932)`, but neither click opened a confirmation dialog; the run halted before ticket 1.
- Failure screenshot shows the unchanged `挑战中` overview, with no ship-depot dialog visible. Do not repeat the same reset click without a new state explanation.
- The first inline behavior-check command was invalid Python because class declarations cannot follow semicolons; reran the check with `type()` fakes successfully.
- Updated `tools/e2e/cases/decisive_stability.py`: only `refresh` invokes `reset_chapter()`; `challenging` is explicitly resumed without chapter reset.

### Stability run health check 2026-09-09 09:07

- The `uv` runner and child Python processes remained alive (runner PID `14692`); the requested serial `127.0.0.1:16384` remained online.
- The active debug log continued through `09:08:20`, during formation/fight recognition in ticket 1 stage 3. The file metadata timestamp lagged behind the flushed log content, so health was judged from fresh tail lines and process/device state.
- No restart or recovery was needed at this checkpoint.

### Stability run health check 2026-09-09 09:22

- Runner PID `14692` and child Python processes remained alive; `127.0.0.1:16384` remained online.
- Ticket 2 continued through combat/fleet transitions; fresh log tail reached `09:23:17` in `FIGHT_PERIOD`.
- No restart or recovery was needed. The open log's filesystem `LastWriteTime` remains stale, so the tail timestamp is the reliable activity signal.

### Stability run health check 2026-09-09 09:37

- Runner PID `14692` and child Python processes remained alive; `127.0.0.1:16384` remained online.
- Fresh log tail reached `09:37:54` while ticket 2 resumed stage 3 after a system retreat. No process restart or manual intervention was needed.

### Stability run guard verification 2026-09-09 09:52

- Restarted the stability case after adding the consecutive system-retreat guard. The new run is active under a new log directory and reached ticket 1 combat after the preserved `challenging` state.
- Runner and child processes are alive; target ADB serial remains online. No guard trigger or restart has occurred in this verification run yet.

### Stability run stop 2026-09-09 09:47

- Ticket 1 completed all 3 stages and 10 drops with the requested 3 leaves and 1 retreat.
- Ticket 2 completed the requested injections, but then entered an unbounded no-ship loop: `PREPARE_COMBAT -> system retreat -> re-enter -> ADVANCE_CHOICE` repeated hundreds of times without another battle.
- The run was stopped with Ctrl+C after preserving the log; cleanup returned the game to the home page. The last runner summary was 604 steps, 0 failed action steps, but overall FAIL because ticket 2 never cleared.
- Added a five-consecutive-system-retreat guard to the stability case; it marks the report halted and exits after the existing restart/recovery attempt instead of looping until the deadline.

### Stability run health check 2026-09-09 10:07

- Runner PID `15860` and child Python processes remained alive; target ADB serial remained online.
- Ticket 3 produced a `WAITING_FOR_MAP` timeout and recovered by restarting the game; ticket 4 continued afterward with all three leaves completed.
- Fresh log content reached `10:08:33`; no continuous-system-retreat guard trigger yet.

### Stability run final 2026-09-09 10:24

- Final run directory: `logs/e2e_tools/decisive_stability/20260909_095023`.
- Final report: 9 tickets attempted, 1 clear, 8 errors, 2 expedition collections, and 8 automatic restart recoveries.
- Added `debug_report.md` with the ticket-2 leave-confirm failure, tickets-3-9 post-combat `WAITING_FOR_MAP` failures, and the prior no-ship loop evidence.
- No E2E runner remains; the game cleanup path returned to the home page. Compile and `git diff --check` passed after the guard change.

### Stability run health check 2026-09-09 10:22

- Runner PID `15860` and child Python processes remained alive; target ADB serial remained online.
- Ticket 9 is active in combat; the latest log tail reached `10:22:36` in `FIGHT_PERIOD`.
- No guard halt or process restart occurred at this checkpoint.
- The previous progress append failed because its anchor text had changed; no file content was altered by that failed patch.

### Confirm exit ROI restriction 2026-09-09

- Added the fixed `CONFIRM_EXIT_ROI` from the user-marked screenshot: `ROI(363/1280, 161/720, 917/1280, 465/720)`.
- `confirm_exit_720p.png` remains the 526x273 crop template; matching is now restricted to that dialog region instead of the full screen.
- Verification: `uv run pytest -q testing/ops/test_decisive_unit.py` -> `20 passed`; `git diff --check` passed.
