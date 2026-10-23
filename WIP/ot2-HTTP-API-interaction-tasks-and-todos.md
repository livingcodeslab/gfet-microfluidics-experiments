# ot2-HTTP-API-interaction — tasks and todos

Progress and backlog for the low-level `gdnasynth.ot2r` client. Design in
`ot2-HTTP-API-interaction-design-notes.md`; findings in
`ot2-HTTP-API-interaction-implementation-notes.md`.

## Working conventions

- The repository is **read-only**; only `patches/` is writable. Work in a
  `/tmp` clone and emit patches to `patches/` per
  `.agents/skills/generating-patches/SKILLS.md`.
- **Tests-first, two patches per function:** one for the tests, one for the
  implementation.
- **pytest** with plain functions + `parametrize`; no `unittest`, no test
  classes.
- Verify with `python3 -m mypy gdnasynth/ot2r/...` and the full test suite.
- Function signatures: **`sender` first, then `run`**.
- Session notes: quasi-immutable history; per-feature
  design/implementation/tasks files (this scheme, adopted 2026-10-23).

## Status snapshot (2026-10-23)

- HEAD `cd46e8e Model protocolId, startedAt and completedAt on Run.`
- 71 tests passing; `mypy` clean.
- No outstanding patches from the client work; everything generated so far is
  merged.

## Done (chronological)

- **2026-10-09:** `RequestSender` + `make_request_sender`; `NonEmptyString`
  subclasses (drop `NewType`); `add_labware_definition`; `Run`/`NormalRun`
  merge; run-result envelope fix (`b0735e7`).
- **2026-10-12:** `parse_labware_offsets` + helpers (`7df66a0`);
  `definitionUri` rename (`eb60d4c`); `LoadedLabware` + `parse_labware`
  (`2eeead4`, `2f20637`); `RunError` / `APIError` (`26914fe`); `Command` +
  `enqueue_command` (`2a77f85`, `36658d3`).
- **2026-10-13:** `to_jsonable` + transport-boundary serialization; setup
  helpers (`load_labware`, `load_pipette`); protocol command helpers; run/
  command state helpers; `send_request` error handling; `sender`-first ordering.
- **2026-10-16:** multipart upload; `upload_protocol`; JSON protocol builder
  (`init_protocol`, `define_liquid`); `singledispatch` `to_jsonable`;
  `create_run(..., protocol_id=None)`; `load_liquid`; `wait_for_resume`;
  `play`/`pause`; `LoadedLabware.id` union fix; `Run` extra fields.
- **2026-10-19:** committed the `Run` field modelling (`cd46e8e`).

## Outstanding (priority order)

**Parsing (older thread, deprioritized while sending/orchestration took focus)**

- [ ] `LocationSequence` → three-way discriminated union
      (`onAddressableArea` / `onModule` / `onLabware`); extend
      `parse_location_sequence`.
- [ ] Parse the remaining `parse_run_result` fields: `pipettes`, `modules`,
      `liquids`, `liquidClasses`, `actions`, `errors`.
- [ ] Finish labware parsing: model `LoadedLabware.location`; add optional
      `offsetId` / `displayName` / `lid_id`.
- [ ] Add `id` / `createdAt` to the offset types; default the optional
      `LegacyLabwareOffsetLocation` fields.
- [ ] Fix the `parse_run_result` comment bug (`parse_modules(result["pipettes"])`
      → `modules`) and the needless list-wrap around `parse_liquid_classes`.

**Sending / commands**

- [ ] Typed command params — the `commandType` / `params` pairing is unchecked.
- [ ] Decide the setup helpers' return shape for the command-id vs resource-id
      ambiguity (or just document it).
- [ ] Verify `None` ⇒ key-omitted against the API before relying on it in
      serialization.
- [ ] Support / verify the `waitUntilComplete` query parameter on
      `POST .../commands` (so a caller can block until the robot executes the
      enqueued command). Relevant to orchestration synchronisation.

**Error handling**

- [ ] `HardwareNotYetInitialized`: decide wait/poll vs fail-fast before
      `create_run` (policy likely belongs to the orchestration layer).

**Housekeeping / deferred**

- [ ] Split `Configuration` into connection vs deck concerns; connection object
      produces the sender.
- [ ] Decide whether `__slots__ = ()` should be added to the string subclasses.

## Future / direction only

- Function-chaining / context-manager ergonomics for call sites.
- Extract a device-neutral transport module (rename `RequestSender` →
  `OpentronsRequestSender` if lifted).
- Modules support and a generic typed `enqueue_command`.
