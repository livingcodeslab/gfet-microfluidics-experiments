# ot2-SMU-orchestration — design notes

The layer above the per-device modules: sequence operations across the OT-2R and
the SMU (and, later, other devices), and persist the data they produce.

**Scope note (2026-10-29):** the serial microfluidics device is **not part of
this design for now**. Mentions of it are retained so we do not forget it, but
it is neither planned nor specified here.

What the orchestrator does **not** know: wells, tips, volumes, pipettes, or how a
run is driven. Those belong to the device's run-control layer
(`ot2-run-control-design-notes.md`); the orchestrator sequences operations and
collects results.

Companion documents:

- `ot2-SMU-orchestration-implementation-notes.md` — what has been built/verified.
- `ot2-SMU-orchestration-tasks-and-todos.md` — docket and todos.
- `ot2-run-control-design-notes.md` — run control, state tracking, steps,
  pre-flight (the OT-2R-specific layer).
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
- The common currency is **operations in domain vocabulary** (e.g. "aspirate
  reagent A", "take an SMU reading"), not device steps and not a shared device
  base class. Device **steps** are internal to each device adapter. Because
  experiment order interleaves devices (aspirate → dispense → acquire →
  dispose), the orchestrator sequences operations it was handed and collects
  their results. *(Revised 2026-10-26 — see §5.)*
- Each device module exposes a small uniform interface — a `Protocol` is
  enough: `execute(operation)`, `flush()`, tear down. Transport details (HTTP
  for the OT-2, VISA/SCPI for the SMU, serial for the microfluidics device) stay
  inside the device module.

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

The *workflow* resolves everything (which device, which reagents, what order)
and hands the orchestrator only operations to sequence.

### Per-device responsibilities the orchestrator delegates

- **Pre-flight / initialisation** — each device has its own; the orchestrator
  invokes it and handles failure (OT-2R specifics:
  `ot2-run-control-design-notes.md` §6).
- **Reset / teardown** — likewise per device.
- **State** — each device owns its own (OT-2R: liquids, tips, steps). The
  orchestrator holds none.


## 3. Data persistence

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

## 4. Work style (2026-10-23 decision)

- **Start small**: singular workflow scripts that **hard-code** their config
  (labware, reagents, tipracks, pipettes).
- As common behaviours emerge, **extract reusable functions**, then extract the
  **config** and the **workflow** (which command runs in what order, and how to
  recover or fail unconditionally when recovery is impossible).

## 5. Levels: operations vs steps, and the barrier model (2026-10-26)

### 5.1 The correction

§2 originally made **device steps** the orchestrator's currency. But an operation
like "aspirate 10 µL of reagent A" and a step like
`Aspirate(pipette, labware, well, volume, flow_rate)` are different vocabularies:

- **domain intent** — experiment terms (reagents, wells, chips, readings);
- **device realization** — plumbing terms (pipettes, labware ids, flow rates).

The orchestrator must never see a `Pipette` or a `flow_rate`.

### 5.2 The levels

| Level | Vocabulary | Owns | Currency |
| --- | --- | --- | --- |
| Workflow | reagents, chips, readings, conditions | experiment logic; may branch on results | operations |
| Orchestrator | device-agnostic scheduling | ordering, barriers, retries, persistence | operations + results |
| Device adapter (OT-2R) | pipettes, labware, wells, tips | config → device binding, device state, planning | steps (internal) |
| Wire | `commandType` / `params` | transport | `Command` |

**Operations are the orchestrator's currency; steps are internal to the device
adapter.** The step / `resolve` / journal machinery (see
`ot2-run-control-design-notes.md` §5) is unchanged — it is simply private
to `ot2r`.

### 5.3 Queued operations vs barriers

The OT-2R run model splits operations into two kinds:

- **Queued operations** (motion: aspirate, dispense, pick tip) — staged into the
  run and executed in FIFO order on `play`; they return nothing now and only
  update the *projected* state.
- **Barrier operations** (SMU reading, microfluidics pump/wash) — synchronous,
  return data, and require the OT-2R queue to be drained first.

So the orchestrator's unit is not a step but a **segment → barrier → segment**
program:

```
stage motion operations ──flush (waitForResume)──► PAUSED
                                                   ├─ run barrier ops (results!)
                                                   └─ decide next segment (adaptive)
resume ── play ──► ...
```

Consequences:

- **Results are first-class.** `resolve → (commands, state)` has no data channel
  because at the device level there is none; data appears at barriers and the
  workflow branches on it.
- **State is per device, never unified.** `RobotState` (liquids/tips) belongs to
  OT-2R (`ot2-run-control-design-notes.md` §5.1); the microfluidics device has its own (primed channels, waste); the SMU
  has none. The orchestrator holds no device state.
- A single domain operation may later decompose across devices (e.g. "deliver
  reagent A to the chip" → OT-2R transfer + microfluidics prime). That is
  workflow/planning work, above the orchestrator.

### 5.4 The seam

```python
# orchestration/
class Device(Protocol):
    def execute(self, operation) -> OpResult | None: ...  # queues, or runs a barrier
    def flush(self) -> None: ...                          # drain staged work to the wire
```

One adapter per device; each interprets only its own operation types. The OT-2R
adapter's **public** surface is operations in domain terms (`aspirate(...)`,
`dispense(...)`, `pick_tip(...)`, `flush(...)`), not steps; its internals are
config binding (reagent → reservoir/well, pipette, flow rate, tip policy),
`RobotState`, `steps`, `resolve`, `execute`.

### 5.5 Staging (avoid premature abstraction)

1. **Now:** `ot2r/liquids.py`, `tips.py`, `state.py` (true at any level), then
   `steps.py` / `execute.py` as a *private device-level mechanism*.
2. **When the first SMU-interleaved workflow exists:** introduce the
   operation/barrier seam with exactly the two devices we actually have.
3. Keep the vocabulary distinct — *operations/actions* vs *steps* — so we do not
   drift back into conflating them.

## 6. Open questions

- [ ] Where does the orchestration live and what is it called? Candidates:
      `gdnasynth/orchestration/` (a layer above `ot2r`) vs
      `gdnasynth/ot2r/session.py`; entity name `Session` / `Orchestrator` /
      `Workflow`.
- [ ] Persistence format (CSV vs JSONL vs both).
- [ ] How much of the workflow (order + recovery policy) to encode as data vs
      code in the early scripts.
- [ ] **Where are the steps/workflows defined?** Hand-written workflow scripts
      (current plan), or a workflow controller/editor? Start with scripts;
      revisit only if they become unwieldy.
- [ ] Which operations may run concurrently (e.g. device initialisation) and
      which must be sequenced (dispense → measure)? The orchestrator needs only
      the ordering, not the details.
