# ot2-SMU-orchestration — tasks and todos

Docket and backlog for the orchestration layer. Design in
`ot2-SMU-orchestration-design-notes.md`; current state in
`ot2-SMU-orchestration-implementation-notes.md`.

## Docket (proposed order, 2026-10-23)

Smallest-useful-first; each new function tests-first (test patch, then impl
patch). Start with pure logic that needs no robot.

- [ ] **1. Liquid ledger.** Volumes per well; `aspirate`/`dispense` updates;
      guards for insufficient source volume and target overflow. Pure logic,
      fully unit-tested.
- [ ] **2. Tip tracking.** Tiprack occupancy per rack/well: pick removes, put
      back restores. Assume full racks initially. Pure logic, unit-tested.
- [ ] **3. Pre-flight + recovery guidance.** Health/hardware check
      (`POST /robot/home`, optionally `/motors/engaged`, `/robot/door/status`)
      and a clear "robot not ready" error with operator recovery steps (X/Y off
      stops / mid-travel, else power-cycle).
- [ ] **4. Orchestrator skeleton.** Wrap a non-protocol normal run: setup
      (labware/pipette), queue commands, pause at SMU points, poll `paused`, call
      an SMU hook, `play` to resume; verify command statuses at the end.
      Generalises `demo_maintenance_run_no_protocol_file.py` into a reusable
      loop.
- [ ] **5. Persistence.** Acquisition returns data; a sink writes it. Reuse
      `take_reading`'s dict + `csv.DictWriter` (see implementation notes §2);
      decide CSV vs JSONL (or CSV + JSONL timeline sidecar).

## Design decisions to settle (see design notes §8)

- [ ] Module location/name: `gdnasynth/orchestration/` vs
      `gdnasynth/ot2r/session.py`; entity name `Session` / `Orchestrator` /
      `Workflow`.
- [ ] Persistence format.
- [ ] How much of the workflow (order + recovery policy) is data vs code in the
      early scripts.
- [ ] Whether to use `/robot/move` for safe positioning before `play`.

## Deferred / later

- [ ] Read each tiprack's real initial state instead of assuming full racks
      (only after the workflow is proven).
- [ ] `pick_next_tip(...)` convenience: resolve the next available tip from a
      named rack (**low priority**). Must handle partially used racks picked
      haphazardly, given a way to enumerate which wells actually hold tips.
- [ ] Robot-side liquid tracking (`loadLiquid`) — blocked by the protocol↔
      enqueue short-circuit; only revisit if the ≥1-command protocol probe
      succeeds.
- [ ] Waste/trash capacity modelling.
- [ ] Contamination rules (tip reuse across wells/channels).
- [ ] Air gaps / hysteresis in aspirate/dispense.

## Dependencies on other features

- **ot2-HTTP-API-interaction:**
  - `waitUntilComplete` enqueue parameter (block until the robot executes) —
    needed for clean synchronisation.
  - `HardwareNotYetInitialized` policy (used by pre-flight).
- **ot2-run-control:**
  - Jam-detection heuristic/thresholds.
  - "Do not trust `succeeded`; check command statuses" verification helper.
