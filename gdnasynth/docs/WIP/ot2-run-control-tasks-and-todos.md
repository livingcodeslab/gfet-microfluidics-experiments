# ot2-run-control — tasks and todos

Progress and backlog for driving runs and the physical robot. Design in
`ot2-run-control-design-notes.md`; findings in
`ot2-run-control-implementation-notes.md`.

## Done (verified on the robot)

- [x] **2026-10-16** — `waitForResume` accepted; run reports `paused` while
      pending, on both maintenance and normal runs; normal-run `play` cycle
      reaches `paused` → `finishing` → `succeeded`.
- [x] **2026-10-16** — Enqueue-while-paused works (adaptive next commands).
- [x] **2026-10-16** — Characterised the maintenance-run `waitForResume` wedge
      (no `/actions`, `RunNotIdle`, `SetupCommandNotAllowedError`; power-cycle
      only).
- [x] **2026-10-16** — Characterised the on-start homing jam (X at hard stop),
      and the "run jams active after failed homing" wedge.
- [x] **2026-10-19** — Homing-jam recovery confirmed: power-cycle + move X
      carriage to mid-travel.
- [x] **2026-10-19** — Characterised the **protocol-linked short-circuit**
      (`succeeded` with commands `queued`; robot only homed).
- [x] **2026-10-19** — Verified the **non-protocol** full pipeline end-to-end
      (`demo_maintenance_run_no_protocol_file.py`: all commands `succeeded`,
      2 pauses honoured).

## Outstanding

**Synchronisation / enqueue semantics**

- [ ] Verify the `waitUntilComplete` query parameter on
      `POST .../commands` so orchestration can block until the robot has
      caught up. (This underpins the decision to rely on HTTP enqueue instead
      of baking commands into the protocol.)

**Protocol vs enqueue probe (deferred, low priority)**

- [ ] Optional probe: does a protocol with **≥1 baked-in command** avoid the
      short-circuit? Only matters if we ever want robot-side liquids. Currently
      we do not (manual tracking chosen).

**Hardware / pre-flight**

- [ ] Decide jam-detection heuristic/thresholds for the orchestrator
      (e.g. run not progressing with commands `queued` for > N s).
- [ ] Decide whether pre-flight `POST /robot/home` is an automatic gate or
      opt-in.
- [ ] Consider reading `/motors/engaged` and `/robot/door/status` in pre-flight.

**State tracking**

- [ ] Track the attached tip's **type** (or its source rack/well), so a tip is
      never returned to a rack of a different tip type — e.g. 200 µL vs 300 µL
      tips on a `p300_single_gen2`. See design notes §4 (gotcha).
- [ ] Implement `ot2r/liquids.py` against the red tests; then `tips.py`,
      `state.py`, `steps.py`, `execute.py` (design notes §5).
- [ ] Review: should `register` refuse once a well holds liquid (set-up-only)?
- [ ] Review: aspirating from a mixture is proportional — an approximation.

**Housekeeping**

- [ ] File the Opentrons bug report (see
      `ot2-run-control-implementation-notes.md` §6): paused-maintenance-run
      wedge; homing-failure run jammed active; protocol-linked `succeeded`
      with commands `queued`; X-homing-at-limit overshoot.
- [ ] Add a "check command statuses, don't trust `succeeded`" helper note to the
      orchestration layer's post-run verification.

## Watch-outs (do not regress)

- Never use `waitForResume` on maintenance runs.
- Never create/`play` a run with X at its hard stop (move to mid-travel first).
- Never assume protocol-linked runs execute HTTP-enqueued commands.
