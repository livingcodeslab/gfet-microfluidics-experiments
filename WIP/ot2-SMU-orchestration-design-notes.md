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

## 9. State model and step/command architecture (2026-10-23)

> **Next session: re-read this section before starting implementation.**

### 9.1 One `RobotState`, not per-concern ledgers

```python
@dataclass(frozen=True)
class RobotState:
    liquids: Liquids          # {labware_id: {well: volume_ul}} (+ capacity)
    tips: Tips                # {rack_id: set of wells still holding a tip}
    tip_on_pipette: bool
```

- **Multiple** liquids and **multiple** tipracks are tracked at once, keyed by
  labware id; each well also carries its capacity (for the overflow guard).
- `tip_on_pipette` is a **boolean**; we do not track where the tip came from.
- Putting a tip back resolves to **the first empty well of a compatible rack**
  (compatibility = the racks configured for that pipette); error if none.

Guards:

- `aspirate`: requires `tip_on_pipette`, `volume > 0`, and
  `available >= volume` (with a tolerance for dead volume).
- `dispense`: requires `tip_on_pipette`, and `target + volume <= capacity` when
  the capacity is known.

### 9.2 The state is a projection of the queued future

A normal run executes queued commands in FIFO order, so folding the state over
the enqueue order is exact. Divergence only arises on failure/abort (§9.4).

### 9.3 `resolve(step, state) -> (commands, new_state)`

A command's parameters can depend on state ("pick a tip" only knows *which
well* once the racks are inspected), so a step cannot precompute its commands.
Collapse `apply` + `commands` into one pure function, implemented as a
`singledispatch` free function (no methods on the dataclasses):

```python
def resolve(step, state) -> tuple[list[Command], RobotState]: ...
```

- Commands and the new state come from the same snapshot, so they cannot
  diverge.
- Dry-run = fold `resolve` and discard the commands; execute = fold `resolve`
  and enqueue the commands.

Step vs Command:

| | `Command` | `Step` |
| --- | --- | --- |
| Nature | wire payload | planning unit |
| Fields | `commandType`, `params`, `intent`, `key` | `name` + data, resolved by `resolve` |
| Knows state | no | yes (guards + state-dependent targets) |
| Emits | — | 1..n commands |
| Failure granularity | one instruction | the atomic unit you choose |

- A step emits >= 1 commands: `waitForResume` -> 1, `trash_tip` -> 2
  (`moveToAddressableAreaForDropTip` + `dropTipInPlace`).
- `transfer` can be **one composite step** (atomic) or **a list of steps**
  (partial progress). How steps are grouped is how failure granularity is
  chosen.

### 9.4 Journal and reconstruction after failure

`execute` returns `(state, journal)`; each journal entry records
`(seq, step, [(command, returned_id)], state_before, state_after)`.

- Projected state = `state_after` of the last step.
- Actual state after failure = `state_before` of the first step whose commands
  are not all `succeeded`; mark that step's touched wells/tips **untrusted**
  rather than guessing.
- Compare actual vs projected and report the divergence.
- Persisting `initial_state` + the journal enables later reconstruction and
  resume.

### 9.5 Consequences for `ot2r`

- Refactor the sender-coupled helpers (`aspirate(sender, run, ...)`, ...) into
  **pure builders** `*_command(...) -> Command`, keeping `enqueue_command` as
  the only sender-touching function. The old wrappers become
  `enqueue_command(sender, run, aspirate_command(...))` and are dropped once
  callers migrate. This keeps one source of truth for payload shapes and lets
  `resolve` stay pure.
- **`intent` must be explicit** (`"protocol"` for motion commands): the server
  defaults it to `"setup"`, and setup commands execute before `play`.
- Correlate commands by the returned `id`; the server assigns `key` = `id`.

### 9.6 Proposed first slice

`gdnasynth/orchestration/`: `state.py` (`RobotState`, `Liquids`, `Tips`),
`liquids.py`, `tips.py`, `steps.py` (step dataclasses + `resolve`
registrations), `execute.py`. Pure-logic tests only: fold a transfer, assert
volumes/tips, assert guards raise, assert `resolve` builds the expected
`Command`s, and assert `execute` with a stub sender applies exactly what it
enqueues.

### 9.7 Open decisions (deferred to next session)

- [ ] Settle `resolve` vs separate `apply` + `commands` (recommendation:
      `resolve`).
- [ ] Start the first test patch for `state.py` / `liquids.py`.
