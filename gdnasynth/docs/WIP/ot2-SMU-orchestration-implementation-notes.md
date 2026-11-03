# ot2-SMU-orchestration — implementation notes

What has actually been built and verified toward the orchestration layer. Design
in `ot2-SMU-orchestration-design-notes.md`; todos in
`ot2-SMU-orchestration-tasks-and-todos.md`.

---

## 1. End-to-end verification on the robot

### 1.1 Protocol-linked demo — fails (short-circuit)

`demo_maintenance_run.py` (repo root) runs the report's *Maintenance Runs* steps
as a **protocol-linked** normal run (3-liquid protocol, custom definition, load
labware/pipette, tip pick/drop, aspirate/dispense, homes, `waitForResume` ×2,
trash tip).

**Result (2026-10-19):** every motion command stayed `queued`; run reported
`succeeded` ~30 s after `play`; robot physically only homed. Cause and evidence:
`ot2-run-control-implementation-notes.md` §5.

### 1.2 No-protocol demo — passes end-to-end

`patches/demo_maintenance_run_no_protocol_file.py` — identical steps, run
created **without** `protocolId` (no protocol upload). Run this from the repo
root with `PYTHONPATH=.`.

**Result (2026-10-19), run id `991338ee-b0d4-4f8f-b722-a29ece6e2024`:** all
commands `succeeded` in order —

```
loadLabware, loadPipette, pickUpTip, dropTip, pickUpTip, aspirate, dispense,
home, waitForResume, aspirate, dispense, aspirate, dispense, home,
waitForResume, aspirate, dispense,
moveToAddressableAreaForDropTip, dropTipInPlace, home
```

Both `waitForResume` pauses were honoured (60 s each, resumed with `play`);
final status `SUCCEEDED`; the robot actually moved. This is the proven pipeline
the orchestration layer should build on.

### 1.3 Robot-side liquids path (verified, but unused going forward)

`init_protocol` + `define_liquid` → `upload_protocol` → `create_run(...,
protocol_id)` (run carries the liquid) → enqueue `loadLabware` + `loadLiquid` →
`play` → both `succeeded` (2026-10-16). Expressibly complete, but incompatible
with HTTP-enqueued command sequencing, so **not** the chosen route.

Note: the engine inserts a `home` command on run start, which is why it appears
in command lists.

### 1.4 The 3-reagent dilution workflow (first full run, 2026-11-02)

`workflow_gfet_smu_dilutions.py` (tracked at the repo root) dilutes 1X PBS to
0.1X / 0.01X / 0.001X / 0.0005X in a `corning_96_wellplate_330ul`, then for each
of two chips acquires all three reagents (water, 0.0005X, 0.001X), washing the
chip between them.

Run `a440881b-0d6f-499e-8970-786a6bb9ac16`: created 18:06:16, started 18:06:44,
**completed 18:38:59** (~32 min); **498 commands, all succeeded**, no errors, no
error recovery. Six CSVs were written, sharing one random suffix.

Verified on hardware: the dilution barrier, `home(axes=["leftZ"])` /
`retract_pipettes`, the wash (5 cycles × 3 mixes), the mux prompt once per chip,
and the `…-chip-N-…` filenames.

**Gate sweep.** `GATE_SWEEP_VOLTAGE = 1.5` — the chip's **absolute maximum
rating**, never exceed it — with `GATE_SWEEP_STEP = 0.1`. The sweep runs from
−1.5 V to +1.5 V **inclusive**, i.e. `float_range(-v, v + step, step)` (without
the `+ step` it stops at −0.1 from the top).

Two client-side defects surfaced and were fixed:

- **The command scan looped forever once every command had succeeded.** A
  `cursor` past the end clamps to the last command (see the HTTP implementation
  notes), so "advance while succeeded" never terminated and the run status was
  never read — the script hung after the run had actually finished. Fixed by
  stopping at `totalLength`.
- **No request timeout.** `send_request` is unbounded unless a timeout is bound;
  the script now builds its sender with `timeout=(10, 60)` (homing keeps
  `(10, 120)`).

## 2. Existing reusable SMU / device code (inventory)

The repository already has acquisition and CSV-writing code to reuse
(2026-10-23 decision):

| Path | What it gives us |
| --- | --- |
| `gdnasynth/keithley.py` | `initialise_smu(...)` — SMU setup |
| `iss********wisafre.py` | `take_reading(smu, gate_voltage, channel_voltage) -> dict[str, float]` with fixed keys (below); sweep-and-flip logic; `csv.DictWriter` output |
| `sweep.py` | `sweep(...)` generator yielding readings; `csv.DictWriter(fieldnames=…)` |
| `read_smu_continuously.py` | continuous readings, SIGTERM handling, CSV printing |
| `gdnasynth/microfluidics.py` | serial microfluidics device: `Channel`, `prime*`, `wash*`, `vent*`, `collect`, `initialise_microfluidics_device` |
| `gdnasynth/cli/` | shared CLI option/validator helpers for SMU and microfluidics args |

Reading dict keys (the CSV columns):

```
timestamp, provided_gate_voltage, provided_channel_voltage,
drain_voltage, drain_current,
measured_gate_voltage, measured_gate_current
```

So persistence can lean on `take_reading` + `csv.DictWriter` rather than
inventing a format.

## 3. What does *not* exist yet

- No orchestration module. No liquid ledger, no tip tracking, no pre-flight, no
  SMU-interleave loop, no persistence sink. Everything above is the verified
  foundation plus reuse candidates.

## 4. Demos as regression fixtures

- `patches/demo_maintenance_run_no_protocol_file.py` — the reference full-pass
  run; keep it runnable from the repo root (`PYTHONPATH=.`).
- `demo_maintenance_run.py` (repo root) — the failing protocol variant; useful
  as a regression/illustration of the short-circuit.
