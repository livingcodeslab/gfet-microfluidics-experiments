# ot2-run-control — design notes

How we drive runs and handle the physical robot: run types, pausing for external
work (e.g. SMU acquisition), the state we track (liquids and tips), the
step/command architecture, pre-flight, and recovery from wedged states.

This is the **OT-2R-specific** layer. The device-agnostic sequencer lives in
`ot2-SMU-orchestration-design-notes.md`; it never sees wells, tips or volumes.

Companion documents:

- `ot2-run-control-implementation-notes.md` — what the robot actually does.
- `ot2-run-control-tasks-and-todos.md` — progress and backlog.
- `ot2-HTTP-API-interaction-design-notes.md` — the client these decisions use.
- `ot2-SMU-orchestration-design-notes.md` — the consumer (device-agnostic).

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

## 3. The interleave loop

**Non-protocol normal run + HTTP-enqueued commands + `waitForResume`**, with
**manual liquid tracking**. Rationale is in §2 above and §4 below: it is
race-free, adaptive (enqueue-while-paused), and avoids the protocol↔enqueue
short-circuit. The SMU interleave loop is:

1. queue the pipetting up to an SMU point, ending with `waitForResume`;
2. `play`; poll the run until `paused`;
3. take SMU readings;
4. optionally enqueue the *next* commands based on the readings;
5. `play` to resume;
6. repeat; then verify command statuses (do not trust `succeeded` alone).

## 4. Manual state tracking: liquids and tips

**Decision (2026-10-23):** track liquids and tips ourselves, in the run-control
layer — not in the orchestrator, and not in the robot.

Liquids must be manual because a protocol-linked run does not cooperate with
HTTP-enqueued commands (2026-10-19, see the implementation notes), so the chosen
route is a **non-protocol normal run + HTTP-enqueued commands**; `loadLiquid`
requires a protocol-defined liquid, so robot-side liquid tracking is
unavailable.

### Liquids

- A ledger of volumes per well, per labware (model in §5.1).
- `aspirate` decrements the source; `dispense` increments the target.
- Guards: refuse to aspirate more than is present; refuse to overflow a target
  beyond its capacity.

### Tips

- Tiprack occupancy per rack/well: a pick removes a tip; putting a tip back
  restores it.
- **Assumption for now: runs begin with full tipracks.** Reading each rack's real
  initial state is a later improvement (after the workflow is proven).
- Possible future: validate that a tip actually came from a full well, and that
  a return goes to the same well.

### Gotcha: tip *type*, not just tip presence

`tip_on_pipette` as a boolean, plus "the first empty well of a compatible rack"
where "compatible = the racks configured for that pipette", is **not enough**. A
`p300_single_gen2` accepts both 200 µL and 300 µL tips, so a run may legitimately
have two racks of *different tip types* for the same pipette. With only a
boolean we could return a 200 µL tip into the 300 µL rack, or vice versa. At
minimum we must track the **tip type** on the pipette (the tiprack definition /
max volume) and only return a tip to a rack of the same type; tracking the
source rack/well is the stricter alternative. *(Recorded 2026-10-29; to be
designed.)*

### Other state worth considering later (not yet designed)

- Waste/trash capacity (the fixed trash is effectively unlimited for now).
- Per-liquid "contamination" constraints (which channels/wells may share a tip).
- Aspirate/dispense hysteresis and air gaps (if the workflow needs them).

The ledger and tip state are **domain bookkeeping**, not robot state: the robot
is not asked to validate them. Keeping them here means the **orchestrator never
sees wells, tips or volumes**; it only sequences operations.


## 5. State model and step/command architecture (2026-10-23)

> **Next session: re-read this section before starting implementation.**

### 5.1 One `RobotState`, not per-concern ledgers

```python
class LiquidId(uuid.UUID):
    """Identifies a liquid; `str(liquid_id)` is the Opentrons `liquidId` key."""

@dataclass(frozen=True)
class Well:
    components: Mapping[LiquidId, float]    # liquid -> volume_ul (> 0)
    capacity_ul: float                      # mandatory; sum(components) <= capacity_ul

@dataclass(frozen=True)
class Liquids:
    contents: Mapping[LabwareId, Mapping[str, Well]]  # the keys ARE the well set

@dataclass(frozen=True)
class Tips:
    racks: Mapping[RackId, frozenset[str]]  # wells still holding a tip

@dataclass(frozen=True)
class RobotState:
    liquids: Liquids
    tips: Tips
    tip_on_pipette: bool
```

#### Composition (2026-10-27)

A well holds a **multiset of liquids**, not just a volume: `components` maps
each liquid to how much of it is present. An empty well is `components == {}`;
total volume is `sum(components.values())`.

- `dispense(liquid, amount)` adds to that liquid's component — mixing *is*
  addition (2 µL A + 3 µL B -> A=2, B=3, total 5).
- `aspirate(amount)` removes the amount **proportionally from every component**
  (well-mixed assumption). **Known issue, deferred:** real aspiration from a
  mixture does not split perfectly proportionally, and reactions that consume or
  produce volume are not modelled.
- Liquid identity comes from the caller (the protocol/config `liquidId`s); the
  ledger never guesses it. `str(liquid_id)` is used as the protocol key.
- `volume(...)` returns the total; `liquid_volume(...)` returns one component
  (0.0 when absent).
- **Parlance:** we use Opentrons' word *liquid* for these entities; "reagent" is
  prose only. A `Liquid` metadata type (id, display name, description, colour)
  belongs to the workflow config and is deferred.

#### Wells vs contents (2026-10-27)

Three "unknown" states must not be conflated:

| case | meaning | behaviour |
| --- | --- | --- |
| labware never registered | config bug | `UnknownLabwareError` |
| well not in the labware's well set (`M1` in a 96-well plate) | typo | `UnknownWellError` |
| well exists but nothing defined/dispensed yet (`A9`) | normal | empty (`components == {}`) |

`Liquids.contents` is well set *and* contents at once: the set of wells for a
labware is the set of wells that exist. They are seeded as empty wells by

```python
@dataclass(frozen=True)
class WellCapacities:
    """The liquid-holding wells of one labware, and how much each can hold."""
    labware_id: uuid.UUID
    capacities: Mapping[str, float]   # well -> capacity_ul; the keys ARE the wells

def register(liquids: Liquids, wells: WellCapacities) -> Liquids:
    """Seed every well of `wells` as empty, preserving existing contents."""
```

The id and the well set travel together, so one plate's geometry can never be
registered under another plate's id. `register` also rejects re-registering a
`labware_id` with a **different well set** — which is exactly what a
wrong-definition mix-up looks like (96-well A-H x 1-12 vs 384-well A-P x 1-24).

**Open question — `register` on a non-empty labware.** `register` is meant to be
a *set-up* operation, so arguably it should refuse to run once a well holds
liquid, rather than silently preserving it. Current decision: keep preserving
contents and **revisit** (tracked in the tasks file).

Capacities (and the authoritative well list) come from a labware definition
(`wells[*].totalLiquidVolume`, keyed by `ordering`). Sources, best first:

- **Robot**: `GET /runs/{runId}/loaded_labware_definitions` returns the full
  definitions of a run's loaded labware (verified 2026-10-27 against API 26.6.0:
  12 wells, `totalLiquidVolume: 15000` for the reservoir). Populated by
  `loadLabware`, and includes uploaded custom definitions. Normal runs only — on
  a maintenance-run id the route answers `409 RunStopped`.
- **Offline**: `opentrons-shared-data` (standard labware), as a fallback.
- Vendoring definition JSONs works but is not viable long-term.

Staged, pure first:

- `wells_from_definition(labware_id, definition) -> WellCapacities` — works for
  standard and custom definitions alike.
- later `wells_from_labware(labware, loader) -> WellCapacities` — feeds the above
  from the run's loaded definitions (preferred) or `opentrons-shared-data`.

**Why not on `Labware`.** Capacity is not a property of labware: lids, adapters
and aluminium blocks have none, and in a tube rack the *tubes* have capacity,
not the rack. So well/capacity geometry is a separate value
(`WellCapacities`), and non-liquid labware never enters the ledger (tipracks are
tracked by `Tips`). `Labware` stays the load config (name, slot, namespace,
version, id) consumed by `load_labware`.

**Keyed by id, not by model.** Several plates or racks of the *same model* are
separate entries, distinguished by their UUIDs; registering one must not touch
another.

#### Tips

- `tip_on_pipette` is a **boolean**; we do not track where the tip came from.
- Putting a tip back resolves to **the first empty well of a compatible rack**
  (compatibility = the racks configured for that pipette); error if none.
- `Tips` stores only the wells that still hold a tip. A **`pick_next_tip(...)`**
  convenience (resolve the next available tip from a named rack) is a
  **low-priority** item; it must cope with haphazardly used racks, assuming we
  can enumerate which wells actually hold tips.

#### Guards

- `aspirate`: requires `tip_on_pipette`, `volume > 0`, and
  `total volume >= volume` (**exact**; no dead-volume tolerance yet); the amount
  is removed proportionally (see Composition).
- `dispense`: requires `tip_on_pipette`, a `liquid`, `volume > 0`, and
  `total volume + volume <= capacity` (capacity is always known).

#### Assumptions (deliberate simplifications)

- Mixing is **additive**: components are summed (2 µL A + 3 µL B -> A=2, B=3).
- Reactions that consume or produce volume are **not** modelled.
- Aspirating from a mixture removes proportionally across components; this is an
  approximation and a **known issue** (deferred).
- Liquid identity is supplied by the caller (config/protocol `liquidId`s).

### 5.2 The state is a projection of the queued future

A normal run executes queued commands in FIFO order, so folding the state over
the enqueue order is exact. Divergence only arises on failure/abort (§5.4).

### 5.3 `resolve(step, state) -> (commands, new_state)`

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

### 5.4 Journal and reconstruction after failure

`execute` returns `(state, journal)`; each journal entry records
`(seq, step, [(command, returned_id)], state_before, state_after)`.

- Projected state = `state_after` of the last step.
- Actual state after failure = `state_before` of the first step whose commands
  are not all `succeeded`; mark that step's touched wells/tips **untrusted**
  rather than guessing.
- Compare actual vs projected and report the divergence.
- Persisting `initial_state` + the journal enables later reconstruction and
  resume.

### 5.5 Consequences for `ot2r`

- Refactor the sender-coupled helpers (`aspirate(sender, run, ...)`, ...) into
  **pure builders** `*_command(...) -> Command`, keeping `enqueue_command` as
  the only sender-touching function. The old wrappers become
  `enqueue_command(sender, run, aspirate_command(...))` and are dropped once
  callers migrate. This keeps one source of truth for payload shapes and lets
  `resolve` stay pure.
- **`intent` must be explicit** (`"protocol"` for motion commands): the server
  defaults it to `"setup"`, and setup commands execute before `play`.
- Correlate commands by the returned `id`; the server assigns `key` = `id`.

### 5.6 Proposed first slice

`gdnasynth/ot2r/`: `liquids.py` (`Well`, `Liquids`, `aspirate`, `dispense`,
`volume`), `tips.py` (`Tips`, `take_tip`, `return_tip`, `first_available`),
`state.py` (`RobotState`), then `steps.py` (step dataclasses + `resolve`
registrations) and `execute.py`. Pure-logic tests only: fold a transfer, assert
volumes/tips, assert guards raise, assert `resolve` builds the expected
`Command`s, and assert `execute` with a stub sender applies exactly what it
enqueues. See §5.8 for why this is `ot2r` and not `orchestration`.

### 5.7 Open decisions (deferred to next session)

- [ ] Settle `resolve` vs separate `apply` + `commands` (recommendation:
      `resolve`).
- [ ] Start the first test patch for `state.py` / `liquids.py`.

### 5.8 Where this code lives

Liquids, tips, wells and tipracks are **OT-2R deck concepts**, so they live in
the device module, not the device-agnostic orchestration layer:

```
gdnasynth/ot2r/
    liquids.py    Well, Liquids, aspirate, dispense, volume
    tips.py       Tips, take_tip, return_tip, first_available
    state.py      RobotState (imports Liquids, Tips)
    steps.py      step dataclasses + resolve         (later)
    execute.py    execute(sender, run, state, steps) (later)

gdnasynth/orchestration/   device-agnostic sequencer: SMU interleaving,
                           persistence, pre-flight; knows nothing of wells
```

Rationale: `resolve(step, state) -> (list[Command], RobotState)` is then entirely
local to `ot2r` (it returns `ot2r.Command` and `ot2r` state, no cross-layer
types). Steps are **internal** to the OT-2R adapter; the orchestrator sees only
operations (see `ot2-SMU-orchestration-design-notes.md` §5). The OT-2R-aware **workflow scripts** import `ot2r`, bind
domain intent to concrete steps, and hand the orchestrator operations to
sequence. This preserves the device boundary while keeping the step types with
their device.

## 6. Pre-flight and recovery guidance

Every device has a pre-flight step before we hand it work. The orchestrator
invokes it but does not know the details
(`ot2-SMU-orchestration-design-notes.md` §2); this section covers the OT-2R.

**[proposed]** `POST /robot/home` (optionally alongside reading `/motors/engaged`
and `/robot/door/status`), and on failure tell the operator how to recover
rather than just erroring.

### Surviving the on-start homing

A normal run **always homes on `play`** (engine hardware preparation),
independent of the queued commands. If the X axis starts at its hard stop,
homing overshoots and halts, and the run becomes unusable (see implementation
notes).

**[proposed]** No API switch skips the on-start homing, so the strategy is:

1. **Pre-flight** — `POST /robot/home` and confirm it completes cleanly *before*
   creating or playing a run. This does not remove the run's own homing but
   catches a bad hardware state early.
2. If coordinates are known, `/robot/move` the axes to a safe position first.
3. **Detect the jam** (run not progressing with commands still `queued` for
   > N s) and **recover**: retry home, move axes off the stops, else power-cycle.
4. **Guidance** — for the observed homing failure (`Out of bounds move: X=… too
   high for limit …` / `ALARM: Kill button pressed`): **move the X (and Y)
   carriage off the hard stops / to roughly mid-travel, then retry; if that
   fails, power-cycle.**

Keeping guidance here (not in `ot2r`) matches the split: `ot2r` surfaces the
failure; the run-control/orchestration layer decides what to show.

### Other devices (when we bring them in)

- **SMU**: pre-flight is `gdnasynth.keithley.initialise_smu(...)` plus
  `gdnasynth.keithley.device_stabilisation(...)` (logging aside). To be written
  up when the SMU joins the workflow.
- Serial microfluidics device: out of scope for now.


## 7. Run lifecycle invariants we rely on

- Enqueuing after a run reaches `stopped` fails with `RunStopped`.
- If you `play` **before** all commands are enqueued, every subsequent enqueue
  must complete before the run finishes, otherwise the API fails with
  `RunStopped`. This is why we queue everything before a single `play`.
- A run reports `paused` while a `waitForResume` is pending; `play` resumes.
- The engine's terminal states are `succeeded`, `failed`, `stopped`.
- **Do not trust a terminal `succeeded` blindly**: a run can report `succeeded`
  with commands still `queued` (observed for protocol-linked runs). Confirm by
  inspecting command statuses (see implementation notes).

## 8. Open questions

- [ ] Verify `waitUntilComplete` on command enqueue (synchronisation).
- [ ] Decide the jam-detection heuristic and thresholds for the run controller.
- [ ] Decide whether pre-flight should be an automatic gate or opt-in.
- [ ] Probe (deferred): does a protocol with ≥1 baked-in command avoid the
      short-circuit? Only relevant if we ever want robot-side liquids.
- [ ] Whether `/robot/move`-based safe positioning is worth using before `play`.
- [ ] **Tip type tracking** (see §4): track the tip type — or the source
      rack/well — so a tip is never returned to a rack of a different tip type.
- [ ] SMU pre-flight: document `gdnasynth.keithley.initialise_smu` /
      `device_stabilisation` when the SMU joins the workflow.
