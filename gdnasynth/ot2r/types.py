"""The data types that will be used for this package."""
import uuid
from dataclasses import field, dataclass
from typing import Literal


HTTPRequestMethod = Literal[
    # Not supported: "HEAD", "CONNECT", "OPTIONS", "TRACE"
    "GET", "POST", "PUT", "DELETE", "PATCH"]

Mount = Literal["left", "right"]


@dataclass(frozen=True)
class Labware:
    """The labware to load onto the deck."""
    labware_name: str
    load_slot: int
    labware_id: uuid.UUID = field(default_factory=uuid.uuid4)
    version: int = 1
    namespace: str = "opentrons"


@dataclass(frozen=True)
class Pipette:
    """The pipette to load."""
    pipette_name: str
    mount: Mount
    pipette_id: uuid.UUID = field(default_factory=uuid.uuid4)
