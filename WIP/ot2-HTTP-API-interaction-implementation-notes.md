# ot2-HTTP-API-interaction — implementation notes

What is actually built in `gdnasynth.ot2r`, and what the robot API actually does.
Design rationale lives in `ot2-HTTP-API-interaction-design-notes.md`; progress
in `ot2-HTTP-API-interaction-tasks-and-todos.md`.

Times are UTC. Where a change was merged, the commit is noted.

---

## 1. Module layout (current)

| File | Contents |
| --- | --- |
| `gdnasynth/ot2r/http.py` | `send_request(...)`; `RequestSender` protocol; `make_request_sender(...)`; `RobotUnreachable`, `RobotResponseError` |
| `gdnasynth/ot2r/types.py` | `Configuration`, `LabwareConfig`, `PipetteConfig`, `HTTPRequestMethod`, `Mount` |
| `gdnasynth/ot2r/commands/base_types.py` | `NumericOpentronsVersion`, `NonEmptyString` |
| `gdnasynth/ot2r/commands/types.py` | `OpentronsVersion`, `DefinitionUri`, `AddressableAreaName`, `LabwareOffset(s)`, `LocationSequence`, `DeckSlotName`, `ModuleModel`, `LoadedLabware`, `Command`, `RunError`, `APIError` |
| `gdnasynth/ot2r/commands/runs/runs.py` | `RunType`, `EngineStatus`, `Run`, parsers (`parse_run_result`, `parse_labware`, `parse_labware_offsets`, …), `run_endpoint`, `create_run`, `add_labware_definition`, `enqueue_command`, setup/protocol command helpers, run/command state helpers |
| `gdnasynth/ot2r/protocols.py` | `Protocol`, `init_protocol`, `define_liquid`, `upload_protocol` |
| `gdnasynth/ot2r/serialization.py` | `to_jsonable` (`singledispatch`) |
| `gdnasynth/ot2r/buildconfig.py` | Interactive configuration builder |

## 2. HTTP API essentials (observed)

- Base URL `http://<host>:31950`.
- Headers: `Content-Type: application/json`, `Accept: application/json`,
  `opentrons-version: <2|3|*>`.
- **Every response payload is wrapped in a top-level `data` envelope**
  (`{"data": {...}}`).
- Error payloads have **no `data` key**: `{"errors": [APIError, ...]}`.
- Normal vs maintenance runs differ in (a) endpoint prefix `/runs` vs
  `/maintenance_runs`, and (b) a normal run must be told to *play*, while a
  maintenance run executes commands as they are enqueued.

### Endpoints used

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/runs` or `/maintenance_runs` | Create a run (`protocolId` only on `/runs`) |
| `POST` | `/{runs}/{id}/labware_definitions` | Upload a custom labware definition |
| `POST` | `/{runs}/{id}/commands` | Enqueue a command |
| `GET` | `/{runs}/{id}` | Get a run by id |
| `GET` | `/{runs}/current_run` ¹ | Get the current run |
| `DELETE` | `/{runs}/{id}` | Delete a run |
| `GET` | `/{runs}/{id}/commands` | List commands |
| `GET` | `/{runs}/{id}/commands/{commandId}` | Get one command |
| `POST` | `/{runs}/{id}/actions` | `play` / `pause` / `stop` (normal runs only) |
| `POST` | `/protocols` | Upload a JSON protocol (multipart) |
| `POST` | `/robot/home` | Home the robot (pre-flight) |

¹ Confirm exact path for "current run" per run type.

### Representative payloads (as first observed)

Create a run: `{"data": {"labwareOffsets": []}}`.

Upload a labware definition: the definition JSON itself nested under `data`;
response `{"data": {"definitionUri":
"livingcodeslab/livingcodeslab_graphenea_card_adapter/1"}}`.

Enqueue a command:

```json
{"data": {"commandType": "loadLabware",
          "params": {"location": {"slotName": "1"},
                     "loadName": "livingcodeslab_graphenea_card_adapter",
                     "namespace": "livingcodeslab",
                     "version": 1,
                     "labwareId": "c9c762e1-8205-4ccd-be32-6535fd0e9514"},
          "intent": "setup"}}
```

## 3. Implementation inventory

- **[done 2026-10-09]** `send_request` thin wrapper; `RequestSender` protocol +
  `make_request_sender` injection (`b0735e7`); `NonEmptyString` subclasses
  replacing `NewType`; `add_labware_definition`; `Run`/`NormalRun` merge.
- **[done 2026-10-12]** `parse_labware_offsets` + helpers (`7df66a0`); renamed
  `LabwareOffset.definitionUri` (`eb60d4c`); rudimentary `LoadedLabware` +
  `parse_labware` (`2eeead4`, `2f20637`); `RunError` + `APIError` (`26914fe`);
  `Command` envelope + `enqueue_command` (`2a77f85`, `36658d3`).
- **[done 2026-10-13]** `serialization.py` `to_jsonable` (`7576b3f` tests,
  `1c14e45` impl); serialise at the transport boundary (`e9948c2`, `8b150ee`);
  `load_labware` / `load_pipette` (`a62d73f` tests, `db61c9b` impl); error
  handling in `send_request` (`RobotUnreachable` / `RobotResponseError` /
  `APIError` parsing); protocol command helpers (`pick_up_tip`, `aspirate`,
  `dispense`, `drop_tip`, `home`, `trash_tip`); `sender`-first reordering;
  run/command state helpers (`get_run`, `get_current_run`, `delete_run`,
  `list_commands`, `get_command`).
- **[done 2026-10-16]** multipart support in `send_request`; `upload_protocol`;
  JSON protocol builder (`init_protocol` + `define_liquid`, frozen `Protocol`,
  version-aware converter); `to_jsonable` as `singledispatch`;
  `create_run(..., protocol_id=None)`; `load_liquid`; `wait_for_resume`;
  `play` / `pause`; `LoadedLabware.id` union fix; `Run` models
  `protocolId`/`startedAt`/`completedAt` (HEAD `cd46e8e`).
- **[done 2026-10-13 → 10-19]** optional `well_location` on
  `pick_up_tip`/`aspirate`/`dispense`/`drop_tip`.

Test suite: 71 tests passing, `mypy` clean at HEAD `cd46e8e` (2026-10-19).

## 4. Observed API behaviour and gotchas

- **Command id vs resource id.** The `id`/`key` returned when enqueuing a
  command is the *command* id. For `loadLabware`/`loadPipette` the
  labware/pipette resource id lives in `params.labwareId` / `params.pipetteId`
  (set from our configs) and later in the run's `labware`/`pipettes` lists.
  Easy to conflate in printouts.
- **`HardwareNotYetInitialized`.** Until the device hardware has finished
  initialising, creating/setting up a run fails; `create_run` originally died
  with `JSONDecodeError` (error envelope has no `data`) while
  `GET /maintenance_runs/current_run` returned
  `{"errors": [{"id": "HardwareNotYetInitialized", ...}]}`.
- **1XX/3XX never reach us.** `100 Continue` is handled by urllib3; FastAPI's
  trailing-slash `307` is followed by `requests`, so `send_request` only sees
  final 2XX/4XX/5XX.
- **Protocols ⇒ liquids ⇒ normal runs only.** `loadLiquid` needs a *defined*
  `liquidId`, and liquids come from a protocol. The linkage is `protocolId` in
  the **normal** run create body; there is no separate attach endpoint.
  `MaintenanceRunCreate` has only `labwareOffsets`, so maintenance runs cannot
  reference a protocol. `POST /protocols` is multipart. `loadLiquid` is
  reportedly not flexible enough for our needs (TBD).
- **Protocol-linked run responses.** They include `protocolId`, `startedAt`,
  `completedAt`, `cameraSettings`, and a `labware` list that includes the fixed
  trash (`id: "fixedTrash"`, not a UUID).
- **The engine inserts a `home` command on normal-run start** (hardware
  preparation), independent of the queued commands.
- **Enqueued commands are filled in by the server**: default `wellLocation`
  (`origin`, `offset`), `intent`, `commandAnnotationIds`, etc.
- **Bad ids may not fail until execution**; state checks matter.
- **Enqueue-while-paused is accepted** (201, `queued`) on a normal run paused at
  a `waitForResume`.

## 5. Shipped-surface conflicts and known gaps

- **`LocationSequence`** models only `onAddressableArea` (and assumes
  `addressableAreaName`); `onModule` / `onLabware` raise `ValueError`. Fix: a
  three-way discriminated union `OnAddressableAreaLocationSequence` /
  `OnModuleLocationSequence` / `OnLabwareLocationSequence`.
- **Offset modelling** is `Union[LegacyLabwareOffset, LabwareOffset]`, but the
  API gives every offset a legacy `location` and newer ones *also* a
  `locationSequence`, plus a `vector`. Options: one type with optional `locationSequence`, or
  keep the union and drop the redundant legacy location for newer offsets.
- **Offset types omit `id` / `createdAt`**, which the robot returns.
- **`LegacyLabwareOffsetLocation.moduleModel` / `.definitionUri`** are optional
  in the API but required in our dataclass (no defaults); the parser passes
  `None` explicitly.
- **Rudimentary labware parsing**: `LoadedLabware.location` is a raw `dict`;
  optional `offsetId` / `displayName` / `lid_id` omitted.
- **Minor bugs:** `parse_run_result`'s comment calls
  `parse_modules(result["pipettes"])` (copy/paste; should be `modules`) and
  wraps `parse_liquid_classes([...])` in a list unnecessarily.
- **`None` ⇒ key-omitted** is asserted by serialization but not yet verified
  against the API.
- **`waitUntilComplete`** query parameter on `POST .../commands` not yet
  supported/verified (see design notes §6 and tasks).
