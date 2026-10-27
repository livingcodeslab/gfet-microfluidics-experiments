"""Types specific to runs."""
import enum
import uuid
import datetime
from typing import Any, Optional, Sequence
from dataclasses import field, dataclass

from gdnasynth.ot2r.types import Pipette
from gdnasynth.ot2r.commands.types import LoadedLabware, LabwareOffsets


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
    protocolId: Optional[uuid.UUID] = None
    startedAt: Optional[datetime.datetime] = None
    completedAt: Optional[datetime.datetime] = None
    actions: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type
    errors: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type
    hasEverEnteredErrorRecovery: bool = False
    pipettes: Sequence[Pipette] = field(default_factory=tuple)
    modules: Sequence[Any] = field(default_factory=tuple)  #TODO: Identify type
    labware: Sequence[LoadedLabware] = field(default_factory=tuple)
    liquids: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type
    liquidClasses: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type
    labwareOffsets: LabwareOffsets = field(default_factory=tuple) #TODO: Identify type
    # The fields below are for normal runs only
    ok: bool = False
    runTimeParameters: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type
    outputFileIds: Sequence[Any] = field(default_factory=tuple) #TODO: Identify type
