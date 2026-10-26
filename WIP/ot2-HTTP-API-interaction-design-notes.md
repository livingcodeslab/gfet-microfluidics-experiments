# ot2-HTTP-API-interaction — design notes

Design decisions and rationale for the low-level client that drives the OT-2R
over its HTTP API: `gdnasynth.ot2r` in `gfet-microfluidics-experiments`.

Related documents:

- `ot2-HTTP-API-interaction-implementation-notes.md` — what was built and what
  the API actually does.
- `ot2-HTTP-API-interaction-tasks-and-todos.md` — progress and backlog.
- `ot2-run-control-design-notes.md` — driving runs (pause/resume, homing); sits
  directly on top of this client.
- `ot2-SMU-orchestration-design-notes.md` — the higher layer.

Status tags: **[done]** implemented; **[proposed]** agreed, not yet
implemented; **[future]** direction only; **[open]** undecided.

API behaviour referenced here was first observed in
`projects-tracker/guided-dna-synthesis/reports/report-2026-09-15.org`
(section *Maintenance Runs*).

---

## 1. Goal and scope

Low-level functions that drive the OT-2R over its HTTP API: create a run,
upload custom labware definitions, upload protocols, enqueue commands, and read
run/command state.

Guiding principle: **low-level functions receive everything they need and know
nothing about the rest of the system.** They must not reach into global state, a
UI, or a whole configuration object just to obtain connection details.

The client is the bottom layer; run-control and orchestration live above it.

## 2. Layering and the `sender` seam

**[done]** Command functions do not take a whole `Configuration`. The
connection details they need (`robot_address`, `opentrons_version`) are bound
into a pre-configured request sender that is passed explicitly, keeping
`Configuration` in the higher layer:

```python
class RequestSender(Protocol):
    """Sends a request to the robot, with connection details already bound."""
    def __call__(self, endpoint: str, method: HTTPRequestMethod,
                 data: dict, **kwargs: Any) -> Response: ...

sender = make_request_sender(config.robot_address,
                             config.opentrons_version)

def create_run(sender: RequestSender, runtype: RunType,
               offsets: LabwareOffsets, protocol_id=None) -> Run: ...
def add_labware_definition(sender: RequestSender, run: Run,
                           definition: Path) -> DefinitionUri: ...
```

Rationale:

- Commands stop depending on deck/session concerns they do not use.
- Unit tests pass a stub sender instead of monkeypatching `runs.send_request`
  globally.
- The sender is the single seam between configuration and execution.

Typing: a `Protocol` (not `Callable[..., Response]`, which discards argument
checking). `make_request_sender` builds it with `functools.partial`.

Parameter order: **`sender` first, then `run`** (settled 2026-10-13), e.g.
`create_run(sender, runtype, offsets)`. Applied uniformly and reflected in the
tests.

Style: eschew OO beyond typing/`Protocol`s — stay functional.

**[future]** Function chaining or context-manager-like patterns may improve
readability once call sites are known.

**[future]** `Configuration` currently serves two roles — *connection*
(`robot_address`, `opentrons_version`) and *deck setup* (labware, pipettes,
custom definitions, protocol file). Extract a connection-level object that
produces the sender, so connection concerns stop leaking into deck
configuration.

## 3. Type design

### Runtime-checked "new" string types

`typing.NewType` is **erased at runtime** — `DefinitionUri(x)` returns `x`
unchanged and performs no checks. So `NewType(..., NonEmptyString)` gave neither
runtime validation nor a runtime-distinct type.

**[done]** Use trivial subclasses of `NonEmptyString` for the distinct string
types (`DefinitionUri`, `AddressableAreaName`, …):

```python
class NonEmptyString:
    __slots__ = ("_value",)
    def __init__(self, value: str) -> None:
        if not value:
            raise ValueError(f"{self.__class__.__name__} cannot be an empty string")
        self._value = value
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._value!r})"
    def __str__(self) -> str:
        return str(self._value)

class DefinitionUri(NonEmptyString):
    """Wraps NonEmptyString to distinguish `DefinitionUri` values"""
```

This inherits the check, keeps the types nominally distinct, and supports
`isinstance()`.

| Approach | Runtime check | Distinct type | `isinstance` | Dedup |
| --- | --- | --- | --- | --- |
| `NewType(..., NonEmptyString)` | no | static only | no | — |
| generic phantom tag | yes | static only | no | yes |
| trivial subclass | yes (inherited) | static + runtime | yes | yes |

**[open]** Subclasses do not declare `__slots__ = ()`, so instances regain a
`__dict__`; add it if the saving matters.

Naming: settled on `DefinitionUri` (not `DefinitionURI`) throughout.

### `Run` and run state

**[done]** `Run` and `NormalRun` were merged into a single `Run` with a custom
`runType` field (not part of the API payload); normal-run-only fields (`ok`,
`runTimeParameters`, `outputFileIds`) keep their defaults.

**[done]** `Run` models `protocolId`, `startedAt`, `completedAt` (parsed, `None`
when absent). Unmodelled response fields (e.g. `cameraSettings`) are ignored by
the parser rather than causing a failure.

**[open]** `parse_run_result` still does not parse the sequence fields
(`pipettes`, `modules`, `liquids`, `liquidClasses`, `actions`, `errors`). See the
tasks file.

### Labware ids

**[done]** `LoadedLabware.id` is `Union[uuid.UUID, NonEmptyString]`: protocol-
linked runs include the fixed trash whose id is the literal string
`"fixedTrash"`, not a UUID. `parse_labware_id` tries a UUID then falls back to a
non-empty string.

## 4. Object → JSON serialization

**[done]** `gdnasynth/ot2r/serialization.py` provides `to_jsonable(...)` as a
`singledispatch`: the default action handles dataclasses (recursing into nested
values), and types register their own converters for leaves.

Design points:

- **`None` ⇒ field omitted.** Several API fields mean "absent key" when `None`
  (e.g. a command's `intent` / `key`). Verify this against the API before
  relying on it. **[open]**
- **Recurse into nested objects** — handled by the dataclass default.
- **Coerce non-JSON leaves** — `datetime.datetime` (ISO-8601), `uuid.UUID`
  (string), and `NonEmptyString` subclasses (→ `str`).
- **Applied at the transport boundary** — `send_request` runs its `data`
  through `to_jsonable`, so every command function simply passes our objects.

## 5. Protocols and liquids (JSON protocol builder)

**[done]** A frozen `Protocol` dataclass is built by `(Protocol, ...) ->
Protocol` functions: `init_protocol(...)`, `define_liquid(...)` (and future
verbs such as `load_labware`, `load_liquid`).

Design points:

- The protocol schema sets `additionalProperties: false`, so serialization
  **must be version-aware**: the registered `to_jsonable` converter emits only
  the sections valid for the schema version and adds `$otSharedSchema`.
- `define_liquid` guards on schema version (liquids need >= 6).
- `upload_protocol(sender, protocol_file, key=None)` is a **multipart file
  upload** (`POST /protocols`); `send_request` gained `files=` support for this.

Note: whether to *use* a protocol at run time is a run-control/orchestration
decision (see `ot2-run-control-implementation-notes.md`). The builder itself is
implemented and verified.

## 6. Error handling

**[done]** `send_request` wraps failures:

- connection failure → `RobotUnreachable`;
- HTTP status >= 400 → `RobotResponseError` carrying status, body, and any
  `APIError`s parsed from an `{"errors": [...]}` envelope.

`RunError` models a protocol-engine error occurrence (a command's `error`, a
run's `errors`); `APIError` models a robot-server HTTP error (`ErrorDetails`).

Design intent: the low layer **surfaces** the failure faithfully; the
orchestration/UI decides how to present it or recover.

**[open]** Special cases: `HardwareNotYetInitialized` (run created before
hardware finished initialising) and bad ids that only fail at execution
(`RunStopped`, bad `pipetteId`).

## 7. Open design questions

Tracked as tasks in `ot2-HTTP-API-interaction-tasks-and-todos.md`:
`LocationSequence` union, remaining `parse_run_result` fields, offset
`id`/`createdAt`, optional legacy-location fields, typed command params,
command-id vs resource-id result shape, `Configuration` split, `__slots__`,
`None`-omission verification, `HardwareNotYetInitialized` policy, and the
`waitUntilComplete` enqueue parameter.

## 8. Package layout — flattening `ot2r` (idea, revisit later)

`gdnasynth.ot2r.commands.runs.runs` nests awkwardly. Possible direction: flatten
into the `gdnasynth.ot2r` package and split **by domain** (liquids, labware,
modules, tips, runs, ...), with a *types* module and a *code* module per domain,
instead of a proliferation of nested packages. Deferred until we understand how
the pieces (especially state/steps) fit together. Tracked in the tasks file.
