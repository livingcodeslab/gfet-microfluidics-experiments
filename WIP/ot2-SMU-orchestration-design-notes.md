# ot2-SMU-orchestration — design notes

The higher layer above `gdnasynth.ot2r`: interleave OT-2R pipetting with SMU data
acquisition (and possibly other devices), while tracking liquids/tips and
persisting data.

Companion documents:

- `ot2-SMU-orchestration-implementation-notes.md` — what has been built/verified.
- `ot2-SMU-orchestration-tasks-and-todos.md` — docket and todos.
- `ot2-run-control-design-notes.md` — how we drive runs (pause/resume, homing).
- `ot2-HTTP-API-interaction-design-notes.md` — the client.

Status tags: **[proposed]** agreed; **[future]**; **[open]**.

---

## 1. Goal

Run a guided-DNA-synthesis / GFET workflow that **interleaves heterogeneous
devices**: aspirate, dispense, take SMU readings, dispose — with the OT-2R doing
the pipetting and a Keithley SMU (and possibly a serial microfluidics device)
doing measurement/fluid handling.

## 2. Multi-device architecture

The guiding split (from the 2026-10-09 design, still current):

- The OT-2-specific pieces (`send_request`, `RequestSender`, `Run`,
  `run_endpoint`, command functions) stay behind a **per-device boundary**; the
  orchestrator never imports them directly.
- The common currency is **steps/commands that target a device**, not a shared
  device base class. Because experiment order interleaves devices
  (aspirate → dispense → acquire → dispose), the orchestrator sequences
  device-bound steps it was handed.
- Each device module exposes a small uniform interface — a `Protocol` is
  enough: set up, execute a step, tear down. Transport details (HTTP for the
  OT-2, VISA/SCPI for the SMU, serial for the microfluidics device) stay inside
  the device module.

### User actions (UI layer)

- choose which robot (if more than one);
- choose which SMU (if more than one);
- specify reagents;
- add / point to custom labware definitions;
- specify the order of events (aspiration, collection, disposal, acquisition, …).

### Program actions

- set up the run: create run → add custom definitions (labware, modules, …) →
  load pipette(s) → load labware → other setup;
- run the experiment in the user-specified order.

The orchestrator resolves everything (which device, which reagents, what order)
and hands each lower layer only what it needs.

## 3. Run control choice

**Non-protocol normal run + HTTP-enqueued commands + `waitForResume`**, with
**manual liquid tracking**. Rationale is in `ot2-run-control-design-notes.md`
§2–3: it is race-free, adaptive (enqueue-while-paused), and avoids the
protocol↔enqueue short-circuit. The SMU interleave loop is:

1. queue the pipetting up to an SMU point, ending with `waitForResume`;
2. `play`; poll the run until `paused`;
3. take SMU readings;
4. optionally enqueue the *next* commands based on the readings;
5. `play` to resume;
6. repeat; then verify command statuses (do not trust `succeeded` alone).

## 4. Manual state tracking

Two kinds of bookkeeping, both in the orchestration layer (the robot is not
asked to validate them):

### Liquids

- Ledger of volumes per well (per labware, per well).
- `aspirate` decrements the source; `dispense` increments the target.
- Guards: insufficient source volume; target overflow beyond capacity.
- Rationale for manual (not robot `loadLiquid`): protocol files short-circuit
  HTTP-enqueued commands (2026-10-19).

### Tips

- Tiprack occupancy per rack/well: a pick removes a tip, putting a tip back
  restores it.
- **Assumption for now: runs begin with full tipracks.** Reading each rack's real
  initial state is a later improvement (after the workflow is proven).
- Possible future: validate that the tip actually came from a full well and that
  a return goes to the same well.

### Other state worth considering later (not yet designed)

- Waste/trash capacity (the fixed trash is effectively unlimited for now).
- Per-liquid "contamination" constraints (which channels/wells may share a tip).
- Aspirate/dispense hysteresis and air gaps (if the workflow needs them).

## 5. Pre-flight and recovery guidance

**[proposed]** The orchestration layer owns a pre-flight step before starting a
run: `POST /robot/home` (optionally alongside reading `/motors/engaged` and
`/robot/door/status`), and on failure tells the operator how to recover rather
than just erroring.

For the observed homing jam (`Out of bounds move: X=… too high for limit …` /
`ALARM: Kill button pressed`), guidance is: **move the X (and Y) carriage off
the hard stops / to roughly mid-travel, then retry; if that fails, power-cycle.**
Keeping guidance here (not in `ot2r`) matches the split: `ot2r` surfaces the
failure; the orchestrator decides what to show.

## 6. Data persistence

- Keep **acquisition decoupled from persistence**: an acquisition step *returns*
  its data; a separate sink (file writer / callback) decides what to do with it.
  The device module knows how to acquire but nothing about file formats.
- **Reuse existing SMU code** (2026-10-23 decision): `iss********wisafre.py`'s
  `take_reading(...)` returns a dict with fixed keys; `sweep.py` writes it with
  `csv.DictWriter`. Column keys:
  `timestamp, provided_gate_voltage, provided_channel_voltage, drain_voltage,
  drain_current, measured_gate_voltage, measured_gate_current`.
- Format to decide: CSV (matches existing tooling/plot scripts) vs JSONL (better
  for mixed event logs). Likely CSV for readings + a JSONL sidecar for the
  command/timeline.

## 7. Work style (2026-10-23 decision)

- **Start small**: singular workflow scripts that **hard-code** their config
  (labware, reagents, tipracks, pipettes).
- As common behaviours emerge, **extract reusable functions**, then extract the
  **config** and the **workflow** (which command runs in what order, and how to
  recover or fail unconditionally when recovery is impossible).

## 8. Open questions

- [ ] Where does the orchestration live and what is it called? Candidates:
      `gdnasynth/orchestration/` (a layer above `ot2r`) vs
      `gdnasynth/ot2r/session.py`; entity name `Session` / `Orchestrator` /
      `Workflow`.
- [ ] Persistence format (CSV vs JSONL vs both).
- [ ] How much of the workflow (order + recovery policy) to encode as data vs
      code in the early scripts.
- [ ] Whether `/robot/move`-based safe positioning is worth using before `play`.
