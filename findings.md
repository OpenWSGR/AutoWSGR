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
- Before the map archive was added, the backend decisive data exposed only `map_end`, `key_points`, and `enemy`; the new per-EX files now provide the route graph and are the runtime source.
- The first mock E2E case design was invalid: it reused the normal entry path and reached `使用上次舰队` before the insufficient-fleet injection, so it did not isolate the requested same-task retreat/re-entry chain. The mock flag was removed without changing production code.
- The captured chapter-6 log proves the advance card was not clicked blindly: `00:34:12.559` detected `advance_choice`, `00:34:12.609` entered `ADVANCE_CHOICE`, then `00:34:12.612` clicked the card and `00:34:13.126` clicked confirm.
- The earlier chapter-1 failure was a different bug: at `00:21:30.224`, missing ship-marker recognition caused the old fallback to force `PREPARE_COMBAT → CHOOSE_FLEET`, which later timed out waiting for `fleet_acquisition`; it did not click an unrecognized advance popup.

## Tomorrow: Event Page False Positive
- `BaseEventPage.is_current_page()` first checks the generic `event/fight_button_20260730_540p.png` at confidence `0.8`.
- On the decisive formation screenshot `logs/e2e_tools/decisive/20260908_034922/images/NavError_034216_477.png`, that matcher returned confidence `0.869940996170044` at normalized center `(0.130078125, 0.050694444444444445)`, which is the top-left back button, not an event attack button.
- Difficulty-icon and event-title checks were both `None`; the false hit won because `EVENT_MAP` is registered before other page candidates.
- Narrow fix for tomorrow: constrain the event fight-button matcher to the real bottom-right activity-button ROI and add an offline regression using this screenshot. Do not change decisive reset or combat logic for this issue.

## Decisive Map Data Semantic Unification (2026-09-09)

- The normal-map contract is one YAML file per map with node keys and `position` plus directed `next` edges. Decisive data should reuse the `next` meaning, but its source does not provide reliable pixel positions, so positions must remain absent until measured from real screenshots.
- `silent_warrior_forward_map.yaml` covers 18 maps (`EX-1-1` through `EX-6-3`), 319 branch-qualified nodes, and 401 directed edges. Node IDs are `0` or `{label}{branch_number}` such as `A1`, `A2`, and `J3`.
- `enemy_formations.yaml` covers the same 18 maps, but keys are base labels (`A` through `J`). Joining is therefore `node_id -> label` by removing the numeric suffix; duplicate branch instances intentionally share the same source formation.
- All 18 route graphs have one terminal base label. Runtime terminal and key-point queries now derive directly from each EX file.
- The current decisive state and DLL recognizer retain only the base node letter, while `get_advance_choice()` always returns index `0`. Route data can be archived now, but branch-qualified tracking and route-aware card selection require a separate state/API decision.
- The supplied enemy data uses human-readable classes (`轻巡`, `驱逐`, `战列`, etc.); the canonical archive maps them through the existing type contract and legacy decisive aliases (`CL`, `DD`, `BB`, `BG`, `BBG`, etc.). In the decisive format, `大巡 -> BG` and `导战 -> BBG`; `机场` is not a normal `ShipType`, so it retains `AF`.
- The old key-point table contained unreachable labels for some shorter maps (for example `J` in `EX-1-3` and `H` in `EX-2-1`); the normalized files retain only reachable key points.
- Added 18 `autowsgr/data/map/decisive_battle/silent_warrior/EX-*.yaml` files as an offline archive only; production loading and state-machine behavior are intentionally unchanged in this phase.
- The leading empty element in legacy enemy arrays is a 1-based compatibility sentinel, not an enemy slot. `MapData.get_enemy()` filters it with `if x`; the new `silent_warrior` files store actual enemy codes only and leave the legacy file untouched.

## Formation Back-Return Root Cause
- The latest `BATTLE_PREP -> MAP` timeout occurs after the back click succeeds; failure screenshots are already on the decisive map.
- `BattlePreparationPage.go_back()` waits for generic `PageName.MAP`, whose tabbed-map checker does not recognize the decisive map layout.
- `DecisiveMapController.is_decisive_map_page()` does recognize that screen, but it is not the checker used by the preparation-page return path.
- The event false positive is a secondary first-frame misclassification; after it disappears, the generic MAP target still returns `None` and causes the timeout.

## Stability Initial-State Diagnosis (2026-09-10)

- The stability E2E runner's normal `prepare()` path calls `_initialize_game()`, which returns the game to the home page before the case starts. That violates the requirement to start from the device's actual state.
- `decisive_stability._reset_after_restart()` immediately calls `detect_entry_status()` without first proving that the current screen is the decisive overview. A main-page device therefore fails before ticket execution.
- `decisive_stability._new_controller()` unconditionally calls `_prepare_entry_state()`, sets `_resume_mode=True`, and forces `ENTER_MAP`; this overwrites an already active decisive map/overlay context.
- A read-only diagnostic at 2026-09-10 04:27 on serial `127.0.0.1:16384` recognized the actual screen as the main page. Decisive map, fleet overlay, advance-choice overlay, and entry status were all absent. The correct next action is normal navigation to the configured decisive chapter, not a reset.
- A decisive map screen does not expose the subsection number through the current map recognizers. If the process starts on an active map and no persisted stage exists, the harness must fail closed rather than assume stage 1/2/3.

## Six-Ticket Stability Run Result (2026-09-10)

- Initial state was detected rather than assumed: main page -> Ex-6 `challenging`, stage 2. The first run reached the real fleet overlay after retreat re-entry; after the state-gating fix, fleet OCR and fallback selection were exercised.
- The chapter reset path passed (`challenging -> reset_button -> confirm -> refreshed`). The clean-start run used `--force-reset-start` only after earlier diagnostic attempts had polluted the partial state.
- No ticket reached combat. Formation scans repeatedly found one usable ship, so the controller correctly entered system retreat at node A. Resetting the chapter did not replenish the actual last fleet; this is a device/configuration precondition failure.
- The expedition interval was 900 seconds and the run stopped before the first interval, so no expedition collection was counted.

## Fleet Primary/Backup Selection Contract (2026-09-12)

- The current `choose_ships()` baseline selected only `config.level1` when the fleet had at most one ship, and only scanned `level2` in the `first_node` branch. `DecisiveState.is_begin()` returns false for Ex-6 stage 2, node A, so the real run selected one primary ship and stopped.
- `logic.py` had no uncommitted changes before this fix; the observed behavior came from the existing branch condition, not the earlier E2E fallback-card change.
- Updated incomplete-fleet candidates to deterministic `level1` first, then configured `level2` ship backups at every node. Full-fleet skill/priority behavior remains separate, and duplicate first-node backup selection is prevented.
- Added tests for non-first-node backup selection and primary-before-backup ordering.

## Fleet Overlay Timeout Root Cause (2026-09-10)

- The failure screenshot from the interrupted six-ticket run is a real `战备舰队获取` page, not an unknown map. Re-saving the same 1280x720 screen with an ASCII filename produced a template score of `0.9999333` inside `FLEET_ACQUISITION_ROI (493, 37, 800, 108)`; thresholds `0.5` through `0.9` all pass.
- The missed detection was state gating: after an earlier entry with no advance-choice popup, `_handle_waiting_for_map()` intentionally set `_fleet_overlay_enabled=False` for temporary-leave recovery. A later retreat reset the map state but `_execute_retreat()` did not re-enable that context flag, so the next advance-choice -> fleet-overlay path skipped fleet recognition entirely.
- Fixed the shared `_execute_retreat()` transition to set `_fleet_overlay_enabled=True` only after retreat confirmation succeeds. `_execute_leave()` remains false. Added a regression test for the two opposite transitions.
- The original E2E failure screenshots were zero-byte files because the failure step label contained `:` in a Windows filename. The E2E framework now sanitizes failure screenshot tags to ASCII-safe names.

## Fleet Close Requires A Selected Card (2026-09-10)

- A clean real-device probe reached `CHOOSE_FLEET` with score 10 and no planned purchase. Directly clicking the red `关闭` button left the overlay open; selecting the first card first, then clicking the same close action, closed it successfully (`close_result=True`, `after_close=False`).
- The production handler therefore needs a lowest-cost fallback card when OCR/decision returns no purchase. This is a UI prerequisite, not a template or coordinate issue; the state then keeps `_force_fleet_scan=True` so current-fleet sufficiency is still evaluated.
- Added the fallback and a focused unit test. Empty OCR selections still retain the existing close-failure/retreat fallback.

## Stability Run Reset Failure (2026-09-09)

- The long-run process completed ticket 1, then repeatedly saw entry status `refresh` and failed inside `reset_chapter()` before any confirmation dialog was opened.
- The captured `refresh` overview shows a large bottom-center `重置关卡` button matching `Templates.Decisive.ENTRY_REFRESH` at about `(0.43, 0.88)-(0.63, 0.98)` on 1280x720.
- `reset_button.png` is a small circular-arrow control at about `(0.65, 0.86)-(0.71, 0.96)` on the `challenging` overview; it does not match the bottom-center `refresh` button (offline score in the old ROI: `0.118`).
- The existing `RESET_BUTTON_ROI = ROI(0.64, 0.84, 0.73, 1.0)` is correct for the small control but cannot handle the `refresh` state. `ENTRY_REFRESH` matches the captured refresh page at `0.9856` in a bottom-center ROI.
- The production reset path must recognize either existing reset control before clicking, then use the existing confirmation matcher. No blind fallback click is needed.
- In the first long-run attempt, ticket 2 hit a second failure at `05:09:20`: after the close click, the next preparation check still saw `fleet_acquisition`; the subsequent `CHOOSE_FLEET` retry waited for an overlay that was no longer consistently present and timed out at `05:09:28`.
- The stability harness originally restarted the app to home after this error but did not reset the decisive chapter, so later tickets reused the stale `challenging` state and repeatedly failed the insufficient-fleet path. The harness now re-enters Ex-6, resets `challenging/refresh` to `refreshed`, and halts if that recovery cannot be verified.
- The production fix is to require a fresh second screenshot after a first-frame `fleet_acquisition` hit. If the second frame does not match, the controller discards the stale overlay result and continues normal map recognition.
- A run interrupted between tickets can leave the game in `challenging`; the corrected harness now performs the same reset-and-verify step before ticket 1 as well as after ticket errors.
- The final run reached a full-dock state. `reset_button` was recognized at `(0.684, 0.932)`, but two clicks produced no confirmation; clicking the central challenge button exposed the `舰船船坞已满` dialog. No ship destruction was authorized or performed.
- In the final run, ticket 2 recovery reached `reset_button` recognition but did not produce the confirmation dialog, so recovery correctly failed closed. The harness previously still entered its deadline-only expedition loop after `halted`; this is now fixed to write the report and exit immediately.

## Decisive Preparation Return Fix
- `DecisiveBattlePreparationPage` is the concrete page used by decisive fleet scanning and fleet changes.
- Its inherited `BattlePreparationPage.go_back()` waited for generic `MapPage.is_current_page()`, which does not recognize the decisive map layout.
- Added a decisive-only `go_back()` override using `is_decisive_map_page`; generic campaign/exercise preparation navigation remains unchanged.
- The first rerun still timed out because `is_decisive_map_page()` itself used the stale `decisive_map_540p.png` template; the actual return screenshot scored `0.2687` against the `0.85` threshold.
- The existing `SIG_MAP_PAGE` pixel signature matched that same screenshot 5/5, so `is_decisive_map_page()` now uses `PixelChecker.check_signature` without adding a new asset.
- Offline verification after the final fix: `uv run pytest -q testing/ops` -> `115 passed`; compileall and selected pre-commit hooks passed.
- Final recovery-chain verification passed all 44 steps, including Case 3 map return/temporary leave and Case 4 resume stopping before battle.

## Stability Run Attempt 2026-09-09 08:24

- The run's normal startup recovery successfully returned from the stale map overlay to the home page and navigated back to Ex-6.
- The live overview was `challenging`; the reset icon matched at the expected ROI and click coordinate `(0.684, 0.932)`.
- Two recognition-gated reset clicks left the overview unchanged and never exposed `confirm_1`. The failure screenshot does not show the full-dock dialog seen when the central `挑战中` button was previously clicked.
- This is a distinct unresolved reset-entry behavior: the click target is recognized, but the game ignores it in the current `challenging` state. The next diagnostic should inspect the challenge entry state/interaction rather than retrying the same reset click.

## Confirm Exit Template ROI (2026-09-09)

- `confirm_exit_720p.png` is a 526x273 cropped dialog template, not a full-screen image.
- The user-marked 1280x720 red box is `x=363..916, y=161..464`; the matching ROI uses the exclusive edge `(917, 465)`.
- `detect_decisive_overlay()` now searches `CONFIRM_EXIT` only inside `CONFIRM_EXIT_ROI`; fleet and advance overlay behavior is unchanged.
- The marked screenshot matched at confidence `0.9989` both before and after the ROI restriction.

## Entry Status Template ROI (2026-09-09)

- The four overview entry templates share the bottom-center status button location.
- The user-marked 1280x720 red box is `x=547..813, y=635..704`; `ENTRY_STATUS_ROI` uses the exclusive edge `(814, 705)`.
- The ROI is now used for overview-page recognition, post-chapter entry-status detection, and stage-clear return-to-overview checks.
- On the marked `挑战中` screenshot, `entry_challenging_540p.png` matches at `0.9951`; the other entry templates do not cross the recognition threshold.

## Stage Number Alignment (2026-09-09)

- `recognize_stage()` now returns `i + 1` for the first unfinished marker instead of the zero-based `i`.
- The returned values are now `1/2/3`, aligned with `DecisiveState.stage` and `EX-{chapter}-{stage}.yaml`; unknown chapters still return `0` as an error sentinel.
- Added coverage for first, second, and third/all-complete marker states.

## Chapter Clear Stage Signal (2026-09-09)

- Stage `3` now means the third subsection is active (the first two markers are complete and the third is not).
- All three markers complete now returns `None`, and `_handle_enter_map()` transitions to the existing `CHAPTER_CLEAR` phase without clicking the map-entry button.
- Unknown chapters still return `0` and are rejected by the entry handler.

## Node Context Log (2026-09-09)

- Existing node recognition only logged the bare DLL result (`识别决战节点: A`).
- Added a business-level log after a real node is accepted: `当前进入为章节 {chapter} 小节 {stage} 的 {node} 列`.
- The log is emitted only after `CHOOSE_FLEET` is excluded and the node is assigned to runtime state.

## Temporary Leave Recovery Flow (2026-09-09)

- Production `DecisiveController.run()` starts each invocation with a fresh `DecisiveState`, `_resume_mode=True`, and `_has_chosen_fleet=False`; it does not persist a controller/state object across process restarts.
- `_execute_leave()` only opens the exit dialog and clicks the leave action. The controller then returns `DecisiveResult.LEAVE`; the server task records a successful `leave` result and stops the round. It does not automatically re-enter the decisive map.
- On a later invocation, `_handle_enter_map()` re-enters the currently active subsection from the overview (`CHALLENGING` or `REFRESHED`), then `WAITING_FOR_MAP` checks `USE_LAST_FLEET` (3-second stabilization plus three ROI matches), `ADVANCE_CHOICE` (the annotated ROI variants), fleet acquisition, and finally the decisive map signature.
- A temporary-leave resume with no advance popup therefore routes directly to `PREPARE_COMBAT`. With `state.node == 'U'`, `_handle_prepare_combat()` re-anchors once through the orange ship marker and DLL; the result is logged as the current chapter/subsection/node. Later node movement is logical/map-data based.
- `_resume_mode` then scans the current formation and available ships through `check_fleet()` only when `state.is_begin()` is false. For stage 1 node A, `state.is_begin()` is true and the handler clears `_resume_mode` before the scan; this is a special first-node path and is the main state distinction to review before a recovery redesign.
- The stability E2E case is not the production task contract: it manually calls `_prepare_entry_state()`, reuses one controller, resets only state for retreat, and continues after leave. Its Case 4 verifies the no-popup path and stops on preparation without clicking sortie; the server API itself stops at `LEAVE`.
- Stability evidence: ticket 1 repeatedly re-entered after leave and reached stage 3 node A with `恢复模式: 扫描当前舰队`; the same run later failed in post-combat `WAITING_FOR_MAP`, which is a separate transition-recognition issue.

## Post-combat Node and Overlay Recognition Audit (2026-09-09)

- Node recognition is already a UI-level method, but its responsibilities are mixed: `get_ship_icon_pos()` performs HSV marker localization, `get_ship_icon_pos_with_retry()` waits up to 10 seconds, and `recognize_node()` stabilizes the marker, crops the vertical column, calls the DLL, retries DLL failure, and may return the `CHOOSE_FLEET` sentinel.
- The only production caller of `recognize_node()` is `_handle_prepare_combat()` when `state.node == 'U'`. This means fresh entry/resume can anchor the current node, but post-combat does not re-anchor.
- After combat, `_handle_node_result()` checks the map-data terminal condition, then predicts the next base letter with `chr(ord(current_node) + 1)`, stores `_advance_source_node`, and polls `detect_decisive_phase()` every 0.5 seconds for up to 15 seconds. It does not use the graph to assign the next node ID or call node recognition.
- The post-combat poll already recognizes `ADVANCE_CHOICE` and `CHOOSE_FLEET`, but through the generic entry detector rather than a dedicated post-combat method. A linear next node reaches `PREPARE_COMBAT` through the map-page fallback; a branch reaches `ADVANCE_CHOICE` first.
- Before the ROI integration, `FLEET_ACQUISITION` used `fleet_acq_720p.png` as a full-screen template at confidence `0.70`; unlike `ADVANCE_CHOICE`, it had no ROI restriction. The first overlay path performed a fresh second-screen confirmation, but the map-page fallback's second overlay check routed `FLEET_ACQUISITION` directly to `CHOOSE_FLEET` without the same fresh confirmation.
- `ADVANCE_CHOICE` recognition does use route-aware ROI selection: unknown initial node checks both the two-card and three-card ROIs; a known post-combat source node uses `MapData.get_leftmost_choices()` to choose the expected ROI. A route with one successor falls back to both ROI variants even though no popup is expected.
- The user's four facts align with the intended state machine: first entry expects a possible advance popup before the first node is known; leave-resume expects no popup and must anchor the current node; combat starts only after a node is known; post-combat must resolve advance choice before fleet acquisition or the next preparation page.

## Fleet Overlay Context Gate (2026-09-10)

- Kept `_resume_mode` focused on its existing responsibility: scanning the current formation during recovery. It is not reused as the fleet-overlay switch.
- Added `_fleet_overlay_enabled` as a separate runtime context. New entry, retreat re-entry, and stage transitions set it to `True`; `_execute_leave()` sets it to `False` for same-controller temporary-leave recovery; a non-terminal `NODE_RESULT` sets it back to `True`; terminal results leave it disabled until the next stage begins.
- Threaded the gate through `wait_for_entry_phase()` and `detect_decisive_phase()`. Only temporary-leave re-entry can now reach the map/`PREPARE_COMBAT` without treating `FLEET_ACQUISITION` as an entry condition; normal new entry still keeps fleet detection enabled.
- The effective first-wait gate is stricter than the context flag: before an advance card has been selected, fleet matching is skipped; after `ADVANCE_CHOICE` (`_skip_advance_choice`) or after a post-combat source node exists, fleet matching is enabled. A no-advance map fallback with no source node is classified as temporary-leave recovery and turns the flag off.
- The gate also filters `detect_decisive_overlay()` so a disabled fleet overlay cannot mask an `ADVANCE_CHOICE` result. The fleet ROI/template itself was intentionally left unchanged pending the user's annotated ROI.
- Verification: focused decisive tests `29 passed`; full `testing/ops` suite `133 passed`; compileall and `git diff --check` passed.

## Fleet Overlay ROI and Template (2026-09-10)

- The red title box in the marked 1280x720 screenshot is `(x1=494, y1=38, x2=799, y2=107)` using exclusive lower-right coordinates.
- The resulting ROI is `305x69`. The no-red screenshot was cropped into `autowsgr/data/images/decisive/fleet_acq_720p.png`.
- The runtime matching ROI is intentionally expanded by 1px on every side to `(x1=493, y1=37, x2=800, y2=108)`; the template remains the tighter `305x69` crop.
- The previous `fleet_acq_720p.png` was a `505x62` crop of the bottom refresh/close buttons; it was replaced with the requested title template.
- Applied `FLEET_ACQUISITION_ROI` to overlay detection, `is_fleet_acquisition()`, and `wait_for_overlay(FLEET_ACQUISITION)` so no fleet path searches the full screen.
- Direct OpenCV validation on the source screenshot returned score `1.0` at `(494, 38)`.
- Verification after ROI integration: focused decisive tests `30 passed`; full `testing/ops` suite `134 passed`; compileall and `git diff --check` passed.

## Decisive ROI Padding Audit (2026-09-10)

- Added `ROI.expand_pixels(width, height, padding=1)` and applied one-pixel padding to every fixed decisive template ROI: use-last fleet, fleet name, fleet acquisition, confirm exit, two/three-card advance choices, entry status, and reset controls.
- The runtime fleet ROI remains the padded `(493,37)-(800,108)` around the exact `305x69` template; the other ROIs now use the same helper instead of hand-written unpadded bounds.
- Template-fit audit at 1280x720: all decisive templates fit their padded ROI except legacy `entry_cant_fight_540p.png`, which scales to about `631x71` while the shared entry-status ROI is `269x72`. This is a source-template/ROI contract mismatch, not a one-pixel boundary issue; widening that fixed ROI would defeat the user's annotated location.

## Fleet Acquisition Page Flow Audit (2026-09-10)

- `CHOOSE_FLEET` enters `_handle_choose_fleet()`, which now starts with `_has_chosen_fleet=False` and only commits it after a non-empty purchase decision and successful overlay close.
- The controller waits for the title ROI/template to remain detectable, then holds a stable screenshot for 1 second by sampling every 0.25 seconds.
- Fleet OCR reads the resource score, all visible costs, and eligible card names. Up to three OCR attempts are made; after an empty result it verifies the overlay is still open before retrying.
- The decision layer selects purchases from current score, current fleet count, configured level1/level2 priorities, and first-node rules. If no purchase is selected, it refreshes the offer list once and repeats OCR/selection.
- Each selected card is clicked at its fixed normalized card position; non-skill purchases are added to `state.ships`. The phase is set to `PREPARE_COMBAT` before the close action.
- `close_fleet_overlay()` clicks the fixed close button and polls every 0.2 seconds for up to 5 seconds. It considers the overlay closed when the fleet title template is no longer detected inside the fleet ROI, then waits an additional 1.5 seconds for the semi-transparent overlay/map transition to settle.
- Close failure changes the phase directly to `RETREAT`; it no longer buys an arbitrary first OCR selection.
- An empty purchase decision closes the overlay, sets a one-shot force-current-fleet-scan flag, and enters `PREPARE_COMBAT`. The preparation path then uses existing fleet data to distinguish enough ships from insufficient ships and lets `should_retreat()` decide.
- After a successful close, the next state-machine iteration enters `PREPARE_COMBAT`, which performs another overlay check before formation. The close confirmation still uses title disappearance plus settle time, not a separate formation/sortie ROI.

## Decisive Formation and Retreat Navigation Audit (2026-09-10)

- Purchase audit (2026-09-12): `DecisiveLogic.choose_ships()` only accepts OCR names that exactly match configured `level1`/`level2` ships. In the latest node-E log, score `5` was available, but the first OCR pass returned `549`, `加里波第`, and `防空伞`, and the refreshed pass returned only `549`; none matched the current chapter-6 YAML, so `选择购买: []` is explained by the OCR/config contract rather than a configured backup being skipped.
- Formation audit (2026-09-12): an empty purchase sets `_force_fleet_scan=True`, then `_handle_prepare_combat()` calls `DecisiveMapController.check_fleet()`. `check_fleet()` always enters formation, detects the current fleet, and then always clicks slot 0 to open the ship pool before returning to the map. This is the direct cause of the redundant ship-pool visit even when the current formation is already sufficient.
- After that scan, `_handle_prepare_combat()` enters formation again and compares `state.fleet` with `get_best_fleet()`. The node-E log shows four existing ships were recognized and the target formation matched; the unnecessary pool visit happened inside `check_fleet()`, before the sufficiency decision.

- Implemented boundary: `check_fleet()` returns after a non-empty formation scan, stays on the preparation page, and does not click slot 0 or OCR the ship pool. An empty formation scans the pool and also stays on the preparation page for immediate replacement.
- Preparation recovery now merges scanned/current ships into `state.ships` instead of replacing the accumulated per-round set. Retreat still calls `state.reset()`.
- Regression coverage confirms a non-empty formation skips `click_ship_slot(0)` and ship-list OCR.
- `full_recovery_check=True` now forces the pool scan even when the current formation is non-empty, so an abnormal restart rebuilds context from both formation and pool.
- Real-device pass `logs/e2e_tools/decisive/20260913_001508` completed chapter 6 stages 1-3 with `chapter_clear`; the key empty-formation log shows pool OCR followed by immediate formation replacement without returning to the map.
- The same pass proves stage 3 did fight: it has `小关 3` combat/result pairs for A through J and ends with `小关 3 终止节点 J 已到达`. However, after stage 2 clear the first stage-3 route log was `source=A choices=['B1']`, with no live node recognition.
- Root cause: `_handle_stage_clear()` assigned `state.node='A'` before entering the next subsection. This bypassed the intended `U -> recognize_node() -> A` anchor and made the entry route use A instead of map node 0.
- Fixed the boundary to reset the next subsection to `U`; the next entry now selects from source 0 and recognizes the live first node in preparation.
- Current real overview screenshot `debug/current_decisive_overview.png` shows the first two yellow completion badges and the third subsection at `0/50`. The old three-point logic incorrectly saw all three common node-glow pixels as completed and returned `None`.
- The corrected stage rule treats the three points as node existence: `100 -> stage 1`, `110 -> stage 2`, `111 -> stage 3 or complete`. For `111`, `entry_refresh` means complete; `entry_challenging` plus the reset-button ROI means stage 3 is still active.
- Direct recognition of the real screenshot now returns `STAGE=3`; offline verification passed with decisive tests `50 passed` and full `testing/ops` `154 passed`.
- Follow-up real-device run `logs/e2e_tools/decisive/20260913_012346` recognized `第 3 小节正在进行`, re-anchored `U -> A`, fought A-J, and reached `小关 3 通关`/`chapter_clear` with no E2E failures.
- Map to formation in the normal combat path is `_handle_prepare_combat()` -> `DecisiveMapController.enter_formation()` -> `click_and_wait_for_page(CLICK_FORMATION, BattlePreparationPage.is_current_page)`. The formation page is then checked by the fixed `FLEET_NAME_ROI` title template, with one map-return retry if the title is not detected.
- The same `enter_formation()` is used by `DecisiveMapController.check_fleet()` when recovery scanning needs to read the current formation and available ships.
- Explicit preparation-page back is `DecisiveBattlePreparationPage.go_back()`, which clicks `CLICK_BACK` and waits on the decisive map pixel signature. This is used by formation scanning/E2E return paths.
- Retreat/leave uses a different reverse path: `_execute_retreat()` -> `open_retreat_dialog()` -> `go_to_map_page()` -> raw back click if the decisive map signature is absent -> click `CLICK_RETREAT_BUTTON` -> wait for `CONFIRM_EXIT` -> `confirm_retreat()` clicks `CLICK_RETREAT_CONFIRM`.
- Therefore `open_retreat_dialog()` owns the “编队页回地图再打开撤退确认” behavior; `DecisiveBattlePreparationPage.go_back()` is the explicit preparation-page return helper and is not called by the retreat dialog path.

## Formation Failure Handling Audit (2026-09-10)

- If the formation click itself does not reach the preparation page, `click_and_wait_for_page()` raises `NavigationError`; `enter_formation()` does not catch it, so `DecisiveController.run()` catches it at the top level and returns `DecisiveResult.ERROR`.
- If the preparation page is reached but the decisive fleet title is not recognized, `enter_formation()` returns to the map and retries the formation click once. A second title failure raises `TimeoutError`, which also becomes task `ERROR`.
- Fleet replacement, repair, damage detection, and manual-repair navigation exceptions all propagate out of `_handle_prepare_combat()` and become `ERROR`; there is no automatic return-to-map/retreat recovery around these operations.
- `BattlePreparationPage.start_battle()` only clicks the sortie button. The handler sleeps one second and advances to `IN_COMBAT` without verifying that the combat page was reached, so a sortie click failure is detected later by the combat engine rather than at the preparation boundary.
- The only dedicated formation failure recovery currently implemented is the single title-recognition retry; a general exception cleanup/retreat path is still missing.

## Formation Error Recovery Boundary (2026-09-10)

- Production `DecisiveController.run()` catches formation and other execution exceptions, logs them, and returns `DecisiveResult.ERROR`; it does not call `restart_game()` or reset the decisive chapter.
- The server decisive task records the error result and stops the task at `result.value in {'leave', 'error'}`; no SL/home/reset recovery is performed there.
- The requested restart-and-reset behavior exists in the stability E2E case only: its exception handler calls `_restart_to_home()` and then `_reset_after_restart()`, which resets the chapter when the entry status is `REFRESH` and preserves `CHALLENGING` progress otherwise.
- Therefore a future production exception policy should reuse the startup/restart operations at the task boundary, rather than adding page-specific recovery branches inside formation operations.

## Decisive Task Error Retry (2026-09-10)

- Added a task-boundary retry budget of 3 total controller attempts for `DecisiveResult.ERROR`.
- Every failed attempt runs `restart_game()` plus `ensure_game_ready()` before the next attempt; the final exhausted attempt also leaves the game restarted/initialized before returning task failure.
- `LEAVE` and successful results are not retried. Intermediate ERROR attempts are not added to the task result list; only the final round result is reported.
- Targeted server validation: 4 decisive retry/leave tests passed.
- Full `testing/server/test_task_routes.py` remains blocked by unrelated existing test-environment failures: pytest temp directory permission denied and non-decisive fixtures missing `set_repairing`.

## SL Full Recovery Check (2026-09-10)

- Retry attempts after the first ERROR call `controller.run(full_recovery_check=True)`.
- Full recovery keeps fleet-overlay detection enabled before ADVANCE resolution; a missing ADVANCE popup no longer disables fleet detection in this context.
- The existing `U` node path re-identifies the current node, and `_force_fleet_scan=True` makes preparation scan the current formation/available ships even at the first node.
- Only after node recognition, fleet-overlay handling, current-fleet scan, sufficiency check, formation preparation, and repair/damage checks does the handler clear the full-recovery flag and click sortie.

## 通用战斗链路审查（2026-09-10）

- 决战 `_handle_prepare_combat()` 在编队、维修和血量检测后调用通用 `BattlePreparationPage.start_battle()`；该方法只点击固定的 `CLICK_START_BATTLE` 坐标，不做出征按钮消失或战斗页到达确认。决战处理器随后固定 `sleep(1.0)`，直接把阶段设为 `IN_COMBAT`。
- `CombatEngine` 从 `START_FIGHT` 过渡态开始，首轮候选为 `SPOT_ENEMY_SUCCESS`、`FORMATION`、`FIGHT_PERIOD` 和 `DOCK_FULL`，通过模板/像素签名轮询识别；`START_FIGHT` 自身没有视觉签名。
- 首轮识别的最大等待时间由候选中 `FIGHT_PERIOD` 的 `30s` 决定。超时后 `_try_recovery()` 先固定等待 `3s`，只检查当前计划终态；决战终态是 `RESULT`。检查不到终态就返回 `SL`，随后 `fight()` 直接调用 `restart_game()`。这会把出征后未进入战斗、战斗页过渡帧或识别漏检都压缩成同一个 `SL` 结果。
- 正常通用战斗顺序为：索敌成功 → 敌方编成/阵型识别与规则决策 → 进入战斗或撤退/迂回 → 阵型 → 战斗进行 → 夜战提示（可能跳过）→ 战果页 → 评级、结算血量、MVP → 点击结算页继续。决战使用 `SINGLE` 转移图，战果页是引擎终态。
- `FIGHT_PERIOD` 后等待候选包含 `NIGHT_PROMPT`（默认 `150s`）和 `RESULT`；因此没有夜战弹窗时，战果识别最多要等夜战候选的超时时间，不是固定 15 秒。
- 战果页 `_handle_result()` 已经采集评级、血量、MVP，并调用 `_click_result_until_closed()`：第一下点击把 `RESULT` 推进到 `EXP_SETTLEMENT`。决战的终态仍定义为 `RESULT`，引擎在确认经验页后返回，外层 `_handle_combat()` 的第二次 `click_result()` 是关闭经验结算页，不是简单重复；但第二次点击后只固定等待 `0.3s`，没有验证地图/overlay 到达。
- 当前确认边界更具体：`_click_result_until_closed()` 只在第一次点击后的轮询中识别 `EXP_SETTLEMENT`；虽然 `_result_successors()` 支持 `GET_SHIP`，但决战引擎在 `RESULT` 终态确认经验页后立即结束，外层第二次点击没有调用 `identify_current()`，因此不会确认第二次点击是否进入 `GET_SHIP`，也不会在这里捕获掉落。

## 决战战斗与掉落收口边界（2026-09-10）

- 决战没有独立的战斗引擎；`ops/decisive/handlers.py` 直接导入通用 `run_combat()`，以 `CombatPlan(mode=CombatMode.DECISIVE)` 运行战斗。
- 决战的专属逻辑在战果之后：通用引擎确认 `RESULT -> EXP_SETTLEMENT` 后返回，决战外层再点击一次；非终止节点进入 `NODE_RESULT`，终止节点进入 `confirm_stage_clear()`。
- `confirm_stage_clear()` 在 `map_controller.py` 中额外执行两次强制确认，然后扫描 `GET_SHIP/GET_ITEM` 模板，逐个 OCR 掉落并点击关闭，最后确认回到决战入口页。这是决战看起来“自己处理掉落”的原因，不是独立战斗实现。
- 成功日志 `logs/e2e_tools/decisive/20260909_002610/autowsgr_2026-09-09.log` 证明了该补偿链：节点 J 战果成功后进入小关通关，随后两次 `confirm_*`，再连续收集 10 个掉落，最后回到决战入口页。

## 普通战与决战结算边界对比（2026-09-10）

- 普通战/活动战使用 `NormalFightRunner._do_combat()` 调用同一个 `run_combat()`，但 runner 的 `_handle_result()` 只处理 `DOCK_FULL` 和记录结果，不在外层额外点击结算按钮。
- 普通战/活动战的 `CombatMode` 终态分别是 `MAP_PAGE`/`EVENT_MAP_PAGE`。通用引擎会继续处理 `RESULT -> EXP_SETTLEMENT -> GET_SHIP/终态`，包括掉落 OCR 和掉落页关闭。
- 决战的 `CombatMode.DECISIVE` 终态被配置为 `RESULT`，因此通用引擎在确认经验页后结束；决战外层再裸点一次，并在小关终点用 `confirm_stage_clear()` 自己处理确认弹窗和掉落。
- 因此“普通战也是这么做的吗”的答案是否定的：共享的是战斗引擎，结算收口契约不同。决战把通用引擎的终态提前截在 `RESULT`，再由决战层补偿后续页面。
- 用户随后确认决战由上层负责从经验结算页继续点击是正确边界；此前临时添加的错误 TODO 已移除。

## 战后点击前正向识别保护（2026-09-10）

- `select_advance_card()` 已在点击卡片前强制 `wait_for_overlay(ADVANCE_CHOICE)`；本次保留该保护。
- 发现共享 `DecisiveMapController.enter_formation()` 只记录地图/准备页识别结果，没有用地图识别结果阻止未知页面点击。该入口同时被正常出征和恢复扫描调用，属于共享点击边界。
- 已在 `enter_formation()` 点击前强制 `is_decisive_map_page(screen)`；未识别到决战地图时抛出 `TimeoutError`，不会调用 `click_and_wait_for_page()`。
- 新增未知页面拒绝测试；验证 `testing/ops` `139 passed`，`git diff --check` 通过。

## 经验结算识别与成功返回边界（2026-09-10）

- 原全屏 MVP 模板判据已被用户提供的固定 ROI OCR 方案替代；运行时不再使用全屏 `result_page_540p.png` 判断经验页。
- `_click_result_until_closed()` 点击后每 `0.3s` 轮询一次，单次最多 4 帧；命中 `EXP_SETTLEMENT` 才会记录后继状态。若持续无法识别，当前实现只记录 debug 并返回，不抛异常。
- 决战的通用终态是 `RESULT`。因此在后继识别失败、内部 phase 仍为 `RESULT` 时，`_make_decision()` 仍可能把本轮转成 `FIGHT_END`，`CombatEngine` 返回 `OPERATION_SUCCESS`；这会让上层误以为可以点击经验页后的按钮。
- `OPERATION_SUCCESS` 后决战上层第二次点击也没有验证经验页消失；非终点会进入地图轮询，终点则先按地图数据进入 `STAGE_CLEAR`。因此“点击未生效”时，终点路径尤其可能在未确认页面上继续执行确认点击。
- 决战随后 `_handle_node_result()` 才以 `0.5s` 间隔轮询 `ADVANCE_CHOICE`、战备浮窗和地图阶段，最长 `15s`；这段等待不是战斗结果识别，而是战果点击后的地图/弹窗收口。
- 稳定性报告中的 tickets 3/4/8/9 失败帧在代码上对应战斗识别超时链：30 秒未命中候选 → `SL` → 决战继续进入 `NODE_RESULT` → 后续地图等待超时。失败帧本身命中 `SPOT_ENEMY_SUCCESS` 只能说明超时后的残留页面，不能证明超时瞬间的页面。

## 经验结算 ROI OCR 判据（2026-09-10）

- 根据用户提供的干净经验结算截图，将 1280x720 顶部 `数字 + Exp` 区域定义为 `EXP_SETTLEMENT_ROI = ROI(272/1280, 4/720, 388/1280, 43/720).expand_pixels(1280, 720)`。
- 运行时 OCR 只裁切该 ROI，允许字符为数字和 `EXP`，按 OCR 横向顺序拼接、去除空白并大写化后，必须完整匹配 `\\d+EXP`。
- 经验页必须连续 3 帧 OCR 命中才算稳定识别；确认后额外等待 1 秒，再允许结算点击继续。
- `EXP_SETTLEMENT` 不再配置全屏 `result_page_540p.png` 模板；`wait_for_phase()` 和结算点击复检走运行时 ROI OCR，旧静态识别接口跳过该状态，避免全屏回退。
- 组合测试首次运行受 pytest 临时目录权限影响（5 个既有 event-map 测试 setup error）；经验专项修正后 `25 passed`，`testing/ops` `139 passed`，compileall 和 diff check 通过。
- 真实 EasyOCR 验证：1x 返回 `200 (1.000)` + `Exp (0.999)`；2x 返回 `200 (1.000)` + `Exp (0.488)`；4x 返回 `200 (0.960)` + `EXP (0.596)`；8x 返回 `200 (1.000)` + `EXp (0.563)`。直接调用生产 matcher 连续三次返回 `[False, False, True]`，稳定计数行为符合预期。

## 经验结算增量 OCR 修正（2026-09-10）

- 用户明确要求取消固定三帧完整字符串判定：战果点击后立即进入循环，每 `0.75s` OCR 一次。
- OCR 结果按允许字符增量累加到列表：可先累积 `E`，后续追加 `X`、`P`；同时必须已经识别到数字。列表累积出 `EXP` 且从点击开始经过至少 `1.5s` 后，才确认经验页并额外等待 1 秒。
- 空白可忽略；除 `0123456789EXP`（大小写归一化）之外的字符会使本次 OCR 结果被拒绝，不会被静默过滤后误通过。
- 真实生产循环实测同一截图输出 `200EXP`：约 `0.05s/0.85s/1.64s` 三次累积，第三次确认成功并在 1 秒后返回；专项测试 `27 passed`，`testing/ops` `139 passed`。

## 经验结算一致结果与超时边界（2026-09-10）

- 经验页成功条件已进一步明确为：战果点击后每 `0.75s` OCR；每次形成一个完整 `数字+EXP` 结果并追加到历史 list；最近三个结果必须一致，且总耗时 `>1.5s`。
- 超过 `10s` 仍未得到三个一致结果时，记录错误日志“未能识别到经验结算页”并抛出 `TimeoutError`，进入上层 ERROR 流程。
- 真实截图实测累积结果为 `['200EXP', '200EXP', '200EXP']`，约 `1.63s` 达成一致，随后等待 1 秒。
- 单个结果内部结构已固定为四格 `['2', '0', '0', 'EXP']`；三个结果逐项比较，真实循环日志确认三组四格完全一致，约 `1.96s` 后等待 1 秒。

## 经验结算结果 list 语义修正（2026-09-10）

- 用户澄清：历史 list 的三个槽位分别保存完整数字，例如 `['200', '200', '200']`；`EXP` 是固定格式条件，不进入历史 list。
- 已修正实现和真实验证：日志结果为 `['200', '200', '200']`，约 `1.75s` 达成一致，随后等待 1 秒。
