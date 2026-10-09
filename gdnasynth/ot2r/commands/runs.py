"""Commands concerning runs."""
import enum
import uuid
import datetime
from typing import Any, Sequence
from dataclasses import field, dataclass

from gdnasynth.ot2r.http import send_request
from gdnasynth.ot2r.commands.types import LabwareOffsets
from gdnasynth.ot2r.types import Configuration, PipetteConfig, LabwareConfig

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


@dataclass(frozen=True)
class NormalRun(Run):
    """Type for a non-maintenance run."""
    ok: bool = False
    runTimeParameters: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type
    outputFileIds: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type


## Steps involved in a maintenance run
#
# 1. Create/Register a run ==> create_run(offsets: LabwareOffsets)

def parse_status(val: str) -> EngineStatus:
    """Parse the value into a valid EngineStatus"""
    return {status.value: status for status in EngineStatus}[val]

def parse_run_result(result) -> Run:
    """Parse the response json."""
    _run = {
        **result,
        "createdAt": datetime.datetime.fromisoformat(result["createdAt"]),
        "status": parse_status(result["status"]),
        # TODO: parse all the sequences too.
    }
    if all((key in result.keys() for key in
            ("ok", "runTimeParameters", "outputFileIds"))):
        return NormalRun(**_run)
    return Run(**_run)


def create_run(
        config: Configuration, runtype: RunType, offsets: LabwareOffsets
) -> Run:
    """Create a run on the robot."""
    resp = send_request(
        robot_address=config.robot_address,
        endpoint=f"/{runtype.value}s",
        method="POST",
        opentrons_version=config.opentrons_version,
        data={"data": {"labwareOffsets": offsets}})
    return parse_run_result(resp.json()["data"])

# 2. Setup:
#     a. Upload labware definition file ==> upload_definition
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
