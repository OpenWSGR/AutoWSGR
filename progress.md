# Progress Log

Task ID: 20260907-autowsgr-decisive-debug-6e3a
Task Status: in_progress
Next Step: Extract explicit node re-anchoring, separate post-combat overlay recognition, add focused tests, then run device verification.

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

### Entry status ROI restriction 2026-09-09

- Added `ENTRY_STATUS_ROI = ROI(547/1280, 635/720, 814/1280, 705/720)` from the user-marked overview screenshot.
- Applied the shared ROI to overview recognition, entry-status polling, and stage-clear return recognition.
- Verification: marked screenshot `entry_challenging_540p` confidence `0.9951`; focused decisive tests -> `22 passed`; `git diff --check` passed.

### Stage index alignment 2026-09-09

- Fixed `recognize_stage()` to return one-based subsection numbers for the per-EX map loader.
- Added unit coverage for stage 1, stage 2, and stage 3/all-complete states.
- Verification: `uv run pytest -q testing/ops/test_decisive_unit.py` -> `23 passed`; `git diff --check` passed.

### Chapter clear signal 2026-09-09

- Separated active stage 3 from completed chapter: all-complete progress markers return `None` and enter `CHAPTER_CLEAR` before map entry.
- Added handler coverage to ensure completed chapters do not click into the map.
- Verification: `uv run pytest -q testing/ops/test_decisive_unit.py` -> `24 passed`; `git diff --check` passed.

### Node context logging 2026-09-09

- Added chapter/stage/node context logging after DLL node recognition.
- Log format: `当前进入为章节 {chapter} 小节 {stage} 的 {node} 列`.
- Verification: focused decisive tests -> `24 passed`; `git diff --check` passed.

### Temporary leave recovery audit 2026-09-09

- Traced production recovery from `_execute_leave()` through the next `run()` invocation and the server task wrapper.
- Confirmed `LEAVE` is a terminal result for the current task invocation; automatic re-entry exists only in the E2E stability harness, which manually reuses the controller.
- Confirmed the no-popup re-entry path is `WAITING_FOR_MAP -> PREPARE_COMBAT`, followed by one ship-marker/DLL node anchor when the node is unknown.
- Recorded the stage-1/node-A exception where `_resume_mode` is cleared before `check_fleet()`, plus the prior stability evidence for stage-3 recovery scanning.

### Post-combat recognition audit 2026-09-09

- Confirmed node localization and DLL recognition already exist as `get_ship_icon_pos*()` plus `recognize_node()`, but the orchestration calls them only for `U` in preparation.
- Confirmed post-combat currently predicts the next letter with `chr(...)` and polls the generic phase detector; it has no dedicated post-combat branch/fleet state resolver.
- Confirmed before the ROI change that `FLEET_ACQUISITION` was a full-screen `fleet_acq_720p.png` template at `0.70`; `ADVANCE_CHOICE` was ROI-limited and route-aware.
- Recorded the fresh-frame inconsistency: the direct fleet-overlay path rechecks a fresh screenshot, while the map-page fallback can return `CHOOSE_FLEET` from a single follow-up overlay match.

### Fleet overlay context gate 2026-09-10

- Added `_fleet_overlay_enabled` without changing `_resume_mode` semantics.
- Kept fleet-overlay recognition enabled for new entry, retreat re-entry, and stage transitions; `_execute_leave()` disables it for same-controller temporary-leave recovery, and non-terminal node results enable it again.
- The first wait still checks ADVANCE_CHOICE before fleet acquisition; fleet matching is only enabled after an advance selection or a post-combat source node. A no-advance/no-source map fallback disables the recovery context.
- Passed the gate through entry and map-phase detection, including the overlay matcher itself; left fleet ROI unchanged until user annotation.
- Verification: `uv run pytest -q testing/ops/test_decisive_unit.py` -> `29 passed`; `uv run pytest -q testing/ops` -> `133 passed`; compileall and `git diff --check` passed.
- Validation note: `uv run ruff check ...` could not start because `ruff` is not installed in the current environment.
- One initial test run failed because two SimpleNamespace fixtures lacked `_advance_source_node`; fixtures were corrected and the rerun passed.

### Fleet overlay ROI and template 2026-09-10

- Detected the marked title ROI as `(494,38)-(799,107)` on the 1280x720 source.
- Cropped the no-red source to `autowsgr/data/images/decisive/fleet_acq_720p.png` (`305x69`), replacing the old bottom-button crop.
- Expanded the runtime match ROI by 1px per side to `(493,37)-(800,108)` while keeping the template crop unchanged.
- Applied the ROI to `detect_decisive_overlay()`, `is_fleet_acquisition()`, and `wait_for_overlay()`.
- OpenCV source match: score `1.0`, location `(494,38)`.
- Project `ImageChecker` validation on the no-red source returned `True` with the new ROI.
- Verification: decisive unit tests `30 passed`; full `testing/ops` `134 passed`; compileall and `git diff --check` passed.

### Decisive ROI padding audit 2026-09-10

- Added `ROI.expand_pixels()` and applied one-pixel padding to all fixed decisive template ROIs.
- Rechecked scaled template dimensions at 1280x720. All fit their padded ROI except the legacy `entry_cant_fight_540p.png` versus the shared entry-status ROI; recorded as a separate asset/ROI mismatch.
- Verification: ROI + decisive tests `44 passed`; full `testing/ops` `134 passed`; compileall and `git diff --check` passed.

### Fleet acquisition page flow audit 2026-09-10

- Traced `CHOOSE_FLEET -> stable screenshot -> OCR score/cost/name -> purchase decision -> card clicks -> close click -> title-disappearance polling -> PREPARE_COMBAT`.
- Changed `_has_chosen_fleet` to commit only after a purchase decision and successful close; empty purchase decisions close, force a current-fleet scan, then defer to `should_retreat()`.
- Added a 1.5-second broad settle wait after title disappearance; removed the empty-selection first-card fallback.
- Verification: decisive tests `33 passed`; full `testing/ops` `137 passed`; ROI + decisive tests `47 passed`.

### Formation and retreat navigation audit 2026-09-10

- Traced map -> formation through `DecisiveMapController.enter_formation()` and its fleet-title verification/retry.
- Traced explicit formation -> map through `DecisiveBattlePreparationPage.go_back()`.
- Traced retreat through `_execute_retreat()` -> `open_retreat_dialog()` -> `go_to_map_page()` -> retreat button -> `CONFIRM_EXIT` -> `confirm_retreat()`.

### Formation failure handling audit 2026-09-10

- Confirmed title recognition has one map-return retry.
- Confirmed click/navigation, fleet change, repair, and sortie failures currently bubble to `DecisiveResult.ERROR`; no generic map-return/retreat cleanup exists.
- Confirmed sortie click itself has no page-arrival verification; combat state is entered after a fixed one-second sleep.

### Formation error recovery boundary 2026-09-10

- Confirmed production `DecisiveController.run()` returns `ERROR` after logging; it does not automatically SL/restart/reset.
- Confirmed server task handling stops after an error result.
- Confirmed restart-to-home plus decisive reset is currently implemented by the stability E2E exception recovery only.

### Decisive task ERROR retry 2026-09-10

- Added 3-attempt task-boundary retry for decisive `ERROR`; each failure invokes SL/restart plus `ensure_game_ready`, including the final exhausted attempt.
- `LEAVE` and success remain terminal without retry.
- Targeted server tests: `4 passed`; full `testing/server/test_task_routes.py` has unrelated temp-directory permission and missing-`set_repairing` fixture failures.

### SL full recovery check 2026-09-10

- Passed `full_recovery_check=True` on retry attempts after ERROR.
- SL recovery keeps ADVANCE/FLEET detection enabled, re-anchors the node, forces current-fleet scanning, and only then permits sortie.
- Verification: decisive unit tests `34 passed`; full `testing/ops` `138 passed`; targeted server retry tests `4 passed`; compileall and `git diff --check` passed.

### 通用战斗链路审查 2026-09-10

- 已从决战出征点击追踪到通用 `CombatEngine` 终止：出征页点击、首轮索敌/阵型/战斗状态识别、战斗过程、夜战、战果采集、结算关闭和决战节点结果轮询。
- 已确认当前生产边界：出征点击后仅固定等待 1 秒，没有确认真正进入战斗页；战斗状态识别 30 秒超时后只检查终态并可能转成 `SL`；战果关闭在引擎和决战外层各点击一次，分别负责 RESULT→EXP_SETTLEMENT 与关闭经验页，但外层第二次点击后没有到达验证。
- 新确认：决战外层第二次结算点击没有经过通用识别器；当前只确认了第一次点击到 `EXP_SETTLEMENT`，没有确认第二次点击到 `GET_SHIP` 或决战地图。

### 决战战斗与掉落收口边界 2026-09-10

- 已用生产调用链确认：决战战斗调用通用 `run_combat()`，没有独立战斗引擎。
- 已解释历史上“能成功关闭并收集掉落”的原因：决战外层第二次结算点击后，终止节点进入 `confirm_stage_clear()`，该方法自己执行两次确认、掉落 OCR/关闭和入口页确认。
- 成功实机日志已对齐：`战果成功 -> 小关通关 -> confirm_4 -> confirm_1 -> 10 个掉落 -> 回到决战入口页`。

### 普通战结算边界对比 2026-09-10

- 已确认普通战/活动战不会在外层重复点击结算；通用引擎按 `MAP_PAGE`/`EVENT_MAP_PAGE` 终态继续处理经验页、掉落页和最终页面。
- 决战使用 `RESULT` 作为通用引擎终态，外层再补第二次点击并接管终点掉落，因此决战的结算边界与普通战不一致，是当前重构需要优先统一/明确的地方。
- 用户确认决战上层接管经验结算页点击是正确边界；已移除上一轮临时添加的错误 TODO，未修改运行逻辑。

### 战后点击前正向识别保护 2026-09-10

- 在共享 `autowsgr/ui/decisive/map_controller.py::enter_formation()` 点击编队前增加决战地图正向识别；未知页面直接拒绝点击。
- 新增 `test_enter_formation_refuses_unrecognized_page`，并更新既有编队测试夹具。
- 验证：`uv run pytest -q testing/ops/test_decisive_unit.py` -> `35 passed`；`uv run pytest -q testing/ops` -> `139 passed`；`git diff --check` 通过。

### 经验结算识别与成功返回边界 2026-09-10

- 已确认并替换经验页判据：固定顶部 ROI OCR 校验 `数字 + Exp`；点击后每 `0.3s` 复检，单次最多 4 帧。
- 已确认风险：后继页面 4 帧都未识别时 helper 静默返回；由于决战 phase 仍是 `RESULT`，引擎仍可能返回 `OPERATION_SUCCESS`。决战上层第二次点击也未复核经验页是否关闭。
- 当前仅记录问题，未修改结算行为；后续需要决定失败时返回错误、继续等待还是交由决战上层恢复。
- 当前仅完成审查和记录，尚未修改通用战斗代码。下一步应先决定“出征到达确认”与“战斗识别超时保真/错误边界”是否作为独立批次，再补对应测试。

### 经验结算 ROI OCR 2026-09-10

- 按用户干净截图增加固定顶部 ROI OCR：`数字 + Exp` 格式校验，不再使用经验页全屏模板。
- OCR 每 `0.75s` 循环一次，按 `E/X/P` 增量累积；累积数字和完整 `EXP` 且经过至少 `1.5s` 后才确认经验页，并在确认后等待 1 秒再继续点击。
- 运行时 `wait_for_phase()` 与 `_click_result_until_closed()` 使用 OCR-aware recognizer；保留静态识别 API 兼容，但静态路径不再匹配 EXP 全屏模板。
- 增加 OCR 正/负格式与增量 token 测试。验证：经验与结算专项 `27 passed`；`testing/ops` `139 passed`；compileall、`git diff --check` 通过。
- 实图 OCR 工具验证未完成：Windows 命令行传递中文文件名时路径变乱码，工具在 `imread` 阶段找不到 `经验结算页roi裁切.png`；不是 OCR 判定失败。Fake OCR 格式测试已覆盖正/负结果。
- 已复制截图到 ASCII 临时路径后完成真实 EasyOCR 验证：1x/2x/4x/8x 均识别出数字与 `Exp`；生产 matcher 实测三帧结果为 `[False, False, True]`。中文原路径乱码只影响工具直接读取，未影响识别结果。

### 经验结算一致结果与超时边界 2026-09-10

- 成功条件改为三个追加到 list 的完整 `数字+EXP` 结果一致，且总耗时超过 `1.5s`；不是简单三帧计数。
- `10s` 超时记录“未能识别到经验结算页”并抛出 `TimeoutError`，不返回 `OPERATION_SUCCESS`。
- 真实生产循环验证结果：`['200EXP', '200EXP', '200EXP']`，约 `1.63s` 确认后等待 1 秒；专项测试 `28 passed`，`testing/ops` `139 passed`。
- 单个结果 list 固定为 `[数字0, 数字1, 数字2, EXP]`；真实生产循环输出三组 `['2', '0', '0', 'EXP']`，约 `1.96s` 一致后成功。

### 经验结算结果 list 语义修正 2026-09-10

- 按用户澄清，历史 list 改为只存完整数字：`['200', '200', '200']`；`EXP` 只作为固定格式校验，不占 list 槽位。
- 真实 EasyOCR 生产循环验证输出 `['200', '200', '200']`，约 `1.75s` 达成一致后等待 1 秒；经验专项 `28 passed`，`testing/ops` `139 passed`。
## 2026-09-10 State-preserving stability bootstrap

- Read the active task plan, findings, progress, repository rules, and binding; verified the bound worktree before editing.
- Performed a read-only device diagnostic on `127.0.0.1:16384`; the actual current page was the main page, with no decisive map or overlay match.
- Found two startup assumptions to remove: E2E `prepare()` returns home by default, and the stability case assumes a decisive overview plus `_resume_mode=True`/`ENTER_MAP`.
- Next: add an explicit state-preserving runner mode and a detected-page stability bootstrap; unknown active-map stage must fail closed.
- First patch attempt did not apply because a hunk included comments whose encoding did not match the file; no source changes were made by that attempt. Reapplied using ASCII-only anchors.
- Added `--preserve-state` to the E2E runner and changed decisive stability bootstrap to recognize the current page before navigation. `compileall`, `git diff --check`, argument parsing, and E2E case listing passed.
- Ran the requested six-ticket test until the repeated failure was proven; stopped after ticket 5's same `WAITING_FOR_MAP` failure instead of burning the remaining path. Repeated logs showed retreat re-entry reached `ADVANCE_CHOICE`, then the visible fleet overlay was ignored.
- Re-saved the failure screen with an ASCII tag and measured `FLEET_ACQUISITION` at `0.9999333`; this ruled out template/ROI mismatch and identified `_fleet_overlay_enabled=False` after retreat as the root cause.
- Fixed `_execute_retreat()` to re-enable fleet-overlay recognition and added `test_retreat_reenables_fleet_overlay_for_reentry`. Verification: decisive unit `36 passed`, full `testing/ops` `140 passed`, compileall and diff check passed.
- Enabled `_full_recovery_check=True` in the stability controller bootstrap so an unknown challenging/overlay state checks ADVANCE, fleet, and node evidence before acting.
- A real no-purchase probe showed selecting one lowest-cost card is required before the game accepts the close action. Added lowest-cost fallback selection in `_handle_choose_fleet()` and `test_choose_fleet_uses_low_cost_fallback_card_before_close`. Verification: decisive unit `37 passed`, full `testing/ops` `141 passed`, compileall and diff check passed.
- One fallback patch attempt caused an indentation error in the shared purchase loop; fixed immediately and reran all affected checks successfully.
- Final clean-start stability attempt reset the chapter successfully but still found only one usable last-fleet ship. It was stopped after repeated node-A system retreats; no combat or ticket completion was counted. Partial reports were written under `logs/e2e_tools/decisive_stability/20260910_051504/`.
- Changed `DecisiveLogic.choose_ships()` so every incomplete formation uses ordered `level1` primary candidates followed by `level2` ship backups; added two focused tests. Verification: decisive unit `39 passed`, full `testing/ops` `143 passed`, compileall and diff check passed.

## 2026-09-12 configured fleet fallback removal

- Real-device run reached chapter 6 stage 2 node G and exposed the production lowest-cost arbitrary-card fallback: OCR offered `塞瓦斯托波尔` and `格罗兹尼`, neither configured.
- Removed the fallback from `autowsgr/ops/decisive/handlers.py`.
- Replaced the fallback regression with `test_choose_fleet_does_not_buy_unconfigured_card`.
- Verification: `python -m pytest -q testing/ops/test_decisive_unit.py` -> `40 passed`; `git diff --check` passed.
- Updated production flow: when `to_buy == []` and the first close attempt fails, choose the lowest-cost real ship (excluding configured decisive skill cards), close again, and enter `RETREAT`; a successful first close still proceeds to current-fleet sufficiency checks.
- Added `test_choose_fleet_falls_back_to_low_cost_ship_when_empty_close_fails`.
- Verification: decisive unit `41 passed`; full `testing/ops` `145 passed`; `git diff --check` passed.
- Next: rerun one complete real-device decisive round with the current state-preserving launcher.

## 2026-09-12 decisive fleet priority and repair ordering

- Reworked `DecisiveLogic.choose_ships()` as a decisive-only algorithm: choose an affordable bundle that maximizes new-ship count, prefers primary ships among equal-size bundles, then adds missing primary ships and upgrades only already-acquired primary ships once the pool has six ships.
- First-node purchase logic now explicitly handles the two-ship affordability cases such as `4+4`, `5+5`, and `6+4`.
- Updated `get_best_fleet()` to retain ships already in the current formation even when the context marks them unavailable, so the decisive preparation flow can repair them before the next sortie.
- Added focused coverage for first-node bundles, six-ship priority, primary-only upgrades, and damaged current ships. Decisive unit tests: `46 passed`; full `testing/ops`: `150 passed`.
- No public smart fleet-change module was modified.
- Next: real-device validation of purchase/formation/repair ordering.

## 2026-09-12 purchase and formation audit

- Inspected the current decisive purchase and preparation call chain without changing production code.
- Confirmed the latest node-E log: score `5`, OCR offers did not match configured ships, then `选择购买: []`.
- Confirmed `check_fleet()` opens the formation page and clicks slot 0 before it knows whether the existing formation is sufficient.
- Recorded the next production change boundary: recognize and evaluate the current formation first; open the ship pool only when the target formation is incomplete or a missing configured ship must be found.

## 2026-09-13 current formation gate

- Changed `DecisiveMapController.check_fleet()` to inspect the current formation first and skip ship-pool entry when at least one ship is already assigned.
- Kept the original ship-pool scan, sufficiency check, retreat decision, and formation replacement path for an empty formation.
- Changed preparation recovery to merge `all_ships` into the accumulated per-round state rather than overwrite it.
- Added `test_check_fleet_skips_ship_pool_when_current_formation_has_ships`.
- Verification: focused tests `2 passed`; decisive unit tests `47 passed`; full `testing/ops` `151 passed`; `compileall` and `git diff --check` passed.

## 2026-09-13 full recovery gate and real-device validation

- Added `scan_ship_pool=True` for `full_recovery_check`, including the first-node path; abnormal restart recovery now scans both current formation and ship pool.
- Kept ordinary non-empty formation scans pool-free and changed fleet scanning to remain on the preparation page so replacement starts immediately.
- The first post-change E2E attempt was blocked by the previous interrupted run leaving the device on the ordinary ship-selection page; the old `initialize` case could not run because it imports the removed `autowsgr.application` package.
- Used the current production `restart_game()` and `ensure_game_ready()` path to restore the device, then ran `decisive --preserve-state --with-ocr --times 1`.
- Final real-device result: `logs/e2e_tools/decisive/20260913_001508`, chapter 6 stages 1-3 completed, result `chapter_clear`, E2E `3 steps, 0 failures`.
- Verification after the final changes: decisive unit tests `48 passed`; full `testing/ops` `152 passed`; compileall and diff check passed.

## 2026-09-13 subsection node re-anchor

- Confirmed from the final E2E log that stage 3 did execute A-J, but its entry route incorrectly used `source=A` because stage-clear code carried `node='A'` across the subsection boundary.
- Changed `_handle_stage_clear()` to reset `state.node='U'`; the next subsection now uses map entry source `0` and re-runs live node recognition.
- Added `test_stage_clear_reanchors_next_subsection_from_unknown_node`.
- Verification: targeted node tests `3 passed`; decisive unit tests `49 passed`; full `testing/ops` `153 passed`; compileall and diff check passed.

## 2026-09-13 stage progress status gate

- Reworked `recognize_stage()` so the three existing pixel points represent node existence, not completion.
- Added entry-status ROI checks for the ambiguous all-nodes-present case: `ENTRY_REFRESH` means all three subsections are complete; `ENTRY_CHALLENGING` plus `RESET_BUTTON` means subsection 3 is still active; unknown combinations return `0`.
- Captured the actual device overview to `debug/current_decisive_overview.png`; direct production recognition returns `3`, matching the visible third subsection at `0/50`.
- Verification: stage tests `2 passed`; decisive unit tests `50 passed`; full `testing/ops` `154 passed`; compileall and diff check passed.

## 2026-09-13 remaining stage 3 real-device run

- Started from the actual challenging overview without resetting the chapter.
- Entry detection returned `第 3 小节正在进行`; preparation logged live node recognition `A` after the `U` anchor.
- Completed stage 3 nodes A through J, collected 10 drops, and reached `chapter_clear`.
- E2E result: `3 steps, 0 failures`; log directory `logs/e2e_tools/decisive/20260913_012346`.
