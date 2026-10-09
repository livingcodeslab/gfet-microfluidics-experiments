"""Commands concerning runs."""
import enum
import json
import uuid
import datetime
from pathlib import Path
from typing import Any, Sequence
from dataclasses import field, dataclass

from gdnasynth.ot2r.http import RequestSender
from gdnasynth.ot2r.commands.types import DefinitionURI, LabwareOffsets
from gdnasynth.ot2r.types import PipetteConfig, LabwareConfig

## Notes:
# Difference between normal runs and  maintenance runs are:
# 1. endpoints: /runs vs. /maintenance_runs
# 2. Normal runs need you to trigger 'play', maintenance runs don't
class RunType(enum.Enum):
    """Possible types of runs"""
    NORMALRUN = "run"
    MAINTENANCERUN = "maintenance_run"


class EngineStatus(enum.Enum):
    """Status of a run."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED_BY_OPEN_DOOR = "blocked-by-open-door"
    STOP_REQUESTED = "stop-requested"
    FINISHING = "finishing"
    AWAITING_RECOVERY = "awaiting-recovery"
    AWAITING_RECOVERY_PAUSED = "awaiting-recovery-paused"
    AWAITING_RECOVERY_BLOCKED_BY_OPEN_DOOR = "awaiting-recovery-blocked-by-open-door"
    STOPPED = "stopped"
    FAILED = "failed"
    SUCCEEDED = "succeeded"


@dataclass(frozen=True)
class Run:
    """The type for a run."""
    runType: RunType #Custom field - not expected/used by Opentrons HTTP API
    id: uuid.UUID
    createdAt: datetime.datetime
    status: EngineStatus
    current: bool = False
    actions: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type
    errors: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type
    hasEverEnteredErrorRecovery: bool = False
    pipettes: Sequence[PipetteConfig] = field(default_factory=tuple)
    modules: Sequence[Any] = field(default_factory=tuple)  #TODO: Identify type
    labware: Sequence[LabwareConfig] = field(default_factory=tuple)
    liquids: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type
    liquidClasses: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type
    labwareOffsets: LabwareOffsets = field(default_factory=tuple) #TODO: Identify type
    # The fields below are for normal runs only
    ok: bool = False
    runTimeParameters: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type
    outputFileIds: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type


## Steps involved in a maintenance run
#
# 1. Create/Register a run ==> create_run(offsets: LabwareOffsets)

def parse_status(val: str) -> EngineStatus:
    """Parse the value into a valid EngineStatus"""
    return {status.value: status for status in EngineStatus}[val]


def parse_run_result(result: dict, runtype: RunType) -> Run:
    """Parse the response json."""
    _run = {
        "runType": runtype,
        **result,
        "createdAt": datetime.datetime.fromisoformat(result["createdAt"]),
        "status": parse_status(result["status"]),
        # TODO: parse all the sequences too.
    }
    return Run(**_run)


def run_endpoint(runtype: RunType) -> str:
    """Return the base HTTP API endpoint for the given type of run."""
    return f"/{runtype.value}s"


def create_run(
        runtype: RunType, offsets: LabwareOffsets, sender: RequestSender
) -> Run:
    """Create a run on the robot.

    :param runtype: The type of run to create.
    :type runtype: gdnasynth.ot2r.commands.runs.RunType
    :param offsets: The initial labware offsets for the run.
    :type offsets: gdnasynth.ot2r.commands.types.LabwareOffsets
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype gdnasynth.ot2r.commands.runs.Run
    """
    resp = sender(
        endpoint=run_endpoint(runtype),
        method="POST",
        data={"data": {"labwareOffsets": offsets}})
    return parse_run_result(resp.json()["data"], runtype)


# 2. Setup:
#     a. Upload labware definition file ==> upload_definition
def add_labware_definition(
        run: Run,
        definition: Path,
        sender: RequestSender
) -> DefinitionURI:
    """Upload a custom labware definition for use by the given run.

    :param run: The run the definition is uploaded for.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param definition: Path to the JSON labware definition file.
    :type definition: pathlib.Path
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype gdnasynth.ot2r.commands.types.DefinitionURI
    """
    resp = sender(
        endpoint=f"{run_endpoint(run.runType)}/{run.id}/labware_definitions",
        method="POST",
        data={"data": json.loads(definition.read_text(encoding="utf-8"))})
    return DefinitionURI(resp.json()["data"]["definitionUri"])


#     b. Load labware
#     c. Load pipette(s)
#     d. Load protocol (to define liquids)
# 3. Enqueue command(s)


## Steps involved in a maintenance run
#
# 1. Create/Register a run ==> create_run(offsets: LabwareOffsets)
# 2. Setup:
#     a. Upload labware definition file ==> upload_definition
#     b. Load labware
#     c. Load pipette(s)
#     d. Load protocol (to define liquids)
# 3. Enqueue command(s)
# 4. "Play" run
#     can occur before enqueue but with gotchas --
#     all subsequent 'enqueue's MUST happen before the run completes
#     otherwise, the command will fail


## Common (extra) functionality:
#
# 1. Get current run (maintenance or otherwise)
# 2. Get a run (by ID -- maintenance or otherwise)
# 3. Delete a run
# 4. Get list of commands in the run
# 5. Get details about specific command in run
#


## Enqueue Command(s)
#
# The command params vary by command type
