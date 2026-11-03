# ot2-run-control — implementation notes

What the robot actually does when driven, and the failure modes we hit. Design
in `ot2-run-control-design-notes.md`; progress in
`ot2-run-control-tasks-and-todos.md`.

Robot: `http://OT2CEP20221010R03:31950`, API 26.6.0, fw `v1.1.0-25e5cea`,
OT-2 Standard.

---

## 1. Normal vs maintenance runs (observed)

- **Maintenance runs auto-execute** commands as they are enqueued; there is no
  `play`. They **do not** appear to home on start (no `Homing` events around a
  maintenance-run `waitForResume`).
- **Normal runs home on `play`** (Protocol Engine hardware preparation), and
  then run the queue.

## 2. `waitForResume` verification (2026-10-16)

- `/openapi.json` includes `waitForResume` (`WaitForResumeCreate`, params
  `{message?}`, `commandType ∈ {waitForResume, pause}`) — firmware accepts it.
- **Maintenance run:** enqueuing `waitForResume` → run `status: "paused"`,
  command `status: "running"`.
- **Normal run** (created with only `labwareOffsets`): enqueue `waitForResume` →
  `play` → run reaches `paused` (command `running`) after the on-start homing
  (~17 s); `play` again → `finishing` → `succeeded`; `DELETE` → 200.
- **Enqueue-while-paused works:** with a normal run paused at `waitForResume`,
  `POST /runs/{id}/commands` accepts a no-motion `comment` (201, `queued`); on
  `play` it executes (both `succeeded`).

## 3. Maintenance runs are a trap (2026-10-16)

`waitForResume` on a maintenance run puts it in `status: "paused"` and it becomes
**unmanageable**:

- `POST /maintenance_runs/{id}/actions` → **404** (no actions endpoint), so it
  cannot be resumed or stopped;
- `DELETE /maintenance_runs/{id}` → `RunNotIdle`;
- further command enqueues → `SetupCommandNotAllowedError`;
- it blocks creating a new maintenance run
  (`500 UnexpectedError` / `RunConflictError: Current run is not idle or
  stopped`).

**Only a power cycle recovered it.** → Never use `waitForResume` on maintenance
runs.

## 4. On-start homing, axis positions, and the jam

- The engine **always homes on normal-run `play`**, independent of the queued
  commands — a no-motion `comment` jams identically.
- **Jam signature:** homing halts — `SmoothieAlarm: ALARM: Kill button pressed -
  reset or M999` → halt → `M999` → halt loop
  (`WARNING: After HALT you should HOME as position is currently unknown`), and
  the run stops progressing.
- **Careful with `Out of bounds move: X=(418.0 motor controller, 419.57 deck) too
  high for limit 418.0`.** It is **also emitted routinely during a normal X
  homing** — 127 occurrences between 2026-09-09 and 2026-11-03, including the
  successful 2026-11-02 run. X homes to `418.0` motor mm, and the `+1.57` mm
  calibration offset maps that to a deck coordinate just past the 418.0 limit. So
  the line **alone is not evidence of a jam**; on 2026-10-19 it merely coincided
  with one, which is how we first read it.
- **2026-10-19 recurrence:** after a power cycle the axes were "off the stops"
  but X was still at `418.0`, so homing halted again (`Recovering from halt`,
  `Homing axes XYZAXZA in sequence ['AZ','X','Y']`) with empty
  `flush_input read: b''` lines in the serial log (flaky serial). **Fix:
  power-cycle *and* move the X carriage to roughly mid-travel** (Y ≈ 350 is
  fine). Homing then completed.

### Axis positions: no live query over HTTP

- No endpoint returns live axis positions. The position-adjacent paths are
  `GET /robot/positions` (calibration targets `change_pipette`, `attach_tip` —
  not live), `GET /motors/engaged` (per-axis engagement), and `POST
  /robot/move` / `POST /robot/home`.
- `GET /logs/serial.log` shows Smoothie `M114.2` position queries, but after a
  halt the controller reports the position as unknown — which is *why* it must
  home.

## 5. Protocol files short-circuit HTTP-enqueued commands (2026-10-19)

**Headline finding.** On a **protocol-linked** normal run (protocol has liquids
but **zero commands**), HTTP-enqueued commands are not executed; the run
`succeeded` right after the on-start homing.

Minimal probes (`waitForResume` / `comment` enqueued via HTTP on a protocol-linked
run):

| Enqueued | Result |
| --- | --- |
| `comment, waitForResume, comment` | both `comment` `succeeded`; `waitForResume` stayed `queued`; run `succeeded` (~32 s after play) |
| `waitForResume, comment` | `waitForResume` stayed `queued`; comment `succeeded` |
| `comment, comment` | both `succeeded` |

Full `demo_maintenance_run.py` (protocol variant): every motion command
(`pickUpTip`, `aspirate`, `dispense`, `home`, `waitForResume`, …) stayed
`queued`; run `succeeded` ~30 s after `play`; the robot **physically only
homed** — statuses were accurate, not stale.

**Without a `protocolId`** (same steps, no protocol file;
`patches/demo_maintenance_run_no_protocol_file.py`): every command `succeeded`,
**both `waitForResume` pauses honoured** (60 s each), final `SUCCEEDED`, and the
robot actually moved (pick/drop tip, aspirate/dispense both chips, trash tip via
`moveToAddressableAreaForDropTip` + `dropTipInPlace`, final home). Run id
`991338ee-b0d4-4f8f-b722-a29ece6e2024`.

**Conclusion:** our client, deck, pipette, and pause/resume loop are fine. A
protocol-linked run whose command list is empty finishes after hardware-prep
homing and abandons the HTTP queue. "Empty command list" is the prime suspect
(as opposed to protocol linkage *per se*); a protocol with ≥1 command has **not**
been tested (deferred).

## 6. Wedged states (candidate Opentrons bug report)

States from which the **only** recovery was a power cycle:

1. **A paused maintenance run is unmanageable** (see §3).
2. **A run whose on-start homing fails jams "active".** The run reports
   `status: "idle"` with its command `queued`, yet the server treats it as
   active: `DELETE /runs/{id}` → `RunNotIdle`; creating a new run →
   `409 RunAlreadyActive`. No `stop`/`play` cleared it; only a power cycle did.
3. **A protocol-linked run reports `succeeded` with commands still `queued`**
   (§5) — silent data loss; callers must inspect command statuses.

Related firmware observation (possible bug in its own right): homing overshoots
when the X axis starts at its hard stop
(`Out of bounds move: X=(418.0 …) too high for limit 418.0` →
`ALARM: Kill button pressed`). Workaround: start with X mid-travel.

**Caveat (2026-11-03):** that `Out of bounds move` line is emitted routinely
during X homing (X homes to 418.0 motor mm, which the +1.57 mm calibration offset
maps just past the deck limit), so its presence alone is not evidence of an
overshoot — the halt and the lack of progress are.

## 7. Practical rules distilled

- Check for active/`idle`-but-jammed runs before creating a new one; a
  `409 RunAlreadyActive` may mean a wedged run, not a live one.
- Never use `waitForResume` on maintenance runs.
- Ensure X (and Y) are off the hard stops, ideally X mid-travel, before `play`.
- Do not treat `succeeded` as proof of completion for protocol-linked runs;
  list commands and check statuses.
- Prefer non-protocol normal runs when commands are enqueued over HTTP.
- **A Smoothie halt surfaces as `SmoothieAlarm: error:Alarm lock`.** 2026-10-30:
  a run halted mid-plunger-move (an `M400` never returned, the next command got
  `error:Alarm lock`, then `M999` → "After HALT you should HOME"); the engine
  marked the running command `failed` with `RunStoppedError: Run was cancelled`.
  The cause is unknown (possibly the kill button) and it did not recur on
  2026-11-02. `/logs/serial.log` is where the halt shows up.
- **A robot lost mid-run leaves the run active.** The client cannot stop or
  delete it while unreachable; once the robot is back, `stop` and `delete` that
  run before starting another — the power loss may also have left it wedged
  (see §6).
- **After an unclean shutdown the front LED can blink and never settle.** A
  forced power-off (hold the button) followed by a power-on clears it. The boot
  itself is healthy: the motor controller and Smoothie connect, the instruments
  are found and `Homing axes ZA` completes. `robot_settings.json` /
  `deck_calibration.json` "not found. Loading defaults" is **normal on this
  robot** (seen on 35 earlier boots) — not a lost calibration.
- **Do not read `Out of bounds move: X=… too high for limit 418.0` as a jam.** It
  is logged on routine X homing (X homes to 418.0 motor mm; the +1.57 mm
  calibration offset pushes the deck coordinate just past the 418.0 limit). A
  real jam adds the halt (`ALARM: Kill button pressed`, `M999`, `Homing fail`)
  and the run stops progressing; the recovery is to move X to mid-travel (or
  power-cycle).
