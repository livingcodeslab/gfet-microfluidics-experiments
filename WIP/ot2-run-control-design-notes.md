# ot2-run-control — design notes

How we *intend* to drive runs and handle the physical robot: choosing run types,
pausing for external work (e.g. SMU acquisition), surviving the on-start homing,
and recovering from wedged states.

Companion documents:

- `ot2-run-control-implementation-notes.md` — what the robot actually does.
- `ot2-run-control-tasks-and-todos.md` — progress and backlog.
- `ot2-HTTP-API-interaction-design-notes.md` — the client these decisions use.
- `ot2-SMU-orchestration-design-notes.md` — the consumer.

Status tags: **[done]** verified/implemented; **[proposed]** agreed;
**[future]**; **[open]**.

---

## 1. Run types

- **Normal run** (`/runs`): must be told to `play`; only a normal run can
  reference a protocol (`protocolId`) and therefore carry protocol-defined
  liquids; exposes `/actions` (`play`/`pause`/`stop`).
- **Maintenance run** (`/maintenance_runs`): executes commands as they are
  enqueued (no `play`); cannot reference a protocol; has **no** `/actions`
  endpoint.

## 2. Pause/resume strategy: decision

We need to hand control to another device (SMU) mid-sequence and then resume.

**Chosen: normal run + everything queued up front, with `waitForResume` markers
at the SMU points.** Enqueue the whole sequence (a `waitForResume` wherever the
SMU runs), `play`, poll the run until `paused`, do the SMU work, `play` to
resume. **[done]** verified on the robot (2026-10-16, non-protocol normal run).

Why this over the alternatives:

1. **No race** — all commands are queued before a single `play`, so the engine
   cannot run ahead of the orchestration code. (Contrast option 2.)
2. **Enqueue-while-paused works** — with the run paused at a `waitForResume`,
   new commands are accepted and execute on `play`. This preserves
   **adaptive** next-command selection based on SMU readings, which a
   fully-baked protocol cannot.
3. **Liquids are (normally) available** — via `protocolId` on the normal run.

Alternatives considered:

2. **Normal run + `pause`/`play` run actions.** Play, pause, enqueue more,
   resume. Timing-sensitive (must pause before the engine runs ahead) — no
   `waitForResume` to pin the boundary.
3. **Several small protocol runs**, one per SMU point, each repeating setup.
   Robust but slow and wasteful.
4. **Maintenance run, no registered liquids, manual well tracking.** Keeps
   step-by-step control but loses protocol liquids; also **`waitForResume`
   wedges a maintenance run** (no `/actions`; see implementation notes) — so
   never use `waitForResume` there.

**Rejected: baking commands into the JSON protocol** to pause at baked-in
`waitForResume`s. It creates a synchronisation nightmare relative to the HTTP
API, and (2026-10-19) a protocol-linked run with an empty command list
short-circuits HTTP-enqueued commands entirely (see implementation notes). The
HTTP-enqueue + `waitForResume` route keeps the orchestration code in control.

See also: investigate the `waitUntilComplete` enqueue parameter so the
orchestration can block until the robot has caught up (open).

## 3. Liquids: manual tracking (decision)

Because a protocol-linked run does not cooperate with HTTP-enqueued commands
(2026-10-19), the chosen route is a **non-protocol normal run + HTTP-enqueued
commands**, with **liquids tracked manually** in the orchestration layer rather
than by the robot (`loadLiquid` requires a protocol-defined liquid).

Liquid-tracking design (owned by the orchestration layer):

- A ledger of volumes per well.
- `aspirate` decrements the source well; `dispense` increments the target.
- Guards: refuse to aspirate more than is present; refuse to overflow a target
  beyond its capacity.
- Tip tracking (same layer): tiprack occupancy — a pick removes a tip, putting
  it back restores it. Initial tiprack state is assumed full for now; reading
  real initial state is a later improvement.

The ledger and tip state are **domain bookkeeping**, not robot state: the robot
is not asked to validate them.

## 4. Surviving the on-start homing

A normal run **always homes on `play`** (engine hardware preparation),
independent of the queued commands. If the X axis starts at its hard stop,
homing overshoots and halts, and the run becomes unusable (see implementation
notes).

**[proposed]** No API switch skips the on-start homing, so the strategy is:

1. **Pre-flight** — `POST /robot/home` (optionally alongside `/motors/engaged`
   and `/robot/door/status`) and confirm it completes cleanly *before* creating
   or playing a run. This does not remove the run's own homing but catches a bad
   hardware state early.
2. If coordinates are known, `/robot/move` the axes to a safe position first.
3. **Detect the jam** (run not progressing with commands still `queued` for
   > N s) and **recover**: retry home, move axes off the stops, else power-cycle.
4. **Pre-flight and recovery guidance belong to the orchestration/UI layer**,
   not to `ot2r`. `ot2r` surfaces failures faithfully (`RobotResponseError`,
   `RunError`); the orchestrator decides what to tell the operator. For the
   observed homing failure the guidance is: **move the X (and Y) carriage off
   the hard stops / to roughly mid-travel, then retry; if that fails,
   power-cycle.**

## 5. Run lifecycle invariants we rely on

- Enqueuing after a run reaches `stopped` fails with `RunStopped`.
- If you `play` **before** all commands are enqueued, every subsequent enqueue
  must complete before the run finishes, otherwise the API fails with
  `RunStopped`. This is why we queue everything before a single `play`.
- A run reports `paused` while a `waitForResume` is pending; `play` resumes.
- The engine's terminal states are `succeeded`, `failed`, `stopped`.
- **Do not trust a terminal `succeeded` blindly**: a run can report `succeeded`
  with commands still `queued` (observed for protocol-linked runs). Confirm by
  inspecting command statuses (see implementation notes).

## 6. Open questions

- [ ] Verify `waitUntilComplete` on command enqueue (synchronisation).
- [ ] Decide the jam-detection heuristic and thresholds for the orchestrator.
- [ ] Decide whether pre-flight should be an automatic gate or opt-in.
- [ ] Probe (deferred): does a protocol with ≥1 baked-in command avoid the
      short-circuit? Only relevant if we ever want robot-side liquids.
