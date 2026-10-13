"""The data types that will be used for this package."""
import uuid
from pathlib import Path
from dataclasses import field, dataclass
from typing import Literal, Sequence, Optional

from gdnasynth.ot2r.commands.types import (OpentronsVersion,
                                           opentrons_version)




HTTPRequestMethod = Literal[
    # Not supported: "HEAD", "CONNECT", "OPTIONS", "TRACE"
    "GET", "POST", "PUT", "DELETE", "PATCH"]

Mount = Literal["left", "right"]


@dataclass(frozen=True)
class LabwareConfig:
    """Config object for labware"""
    labware_name: str
    load_slot: int
    labware_id: uuid.UUID = field(default_factory=uuid.uuid4)
    version: int = 1
    namespace: str = "opentrons"


@dataclass(frozen=True)
class PipetteConfig:
    """The config settings for a pipette."""
    pipette_name: str
    mount: Mount
    pipette_id: uuid.UUID = field(default_factory=uuid.uuid4)


class ConfigurationException(Exception):
    """Raised in case of a problem setting up the configuration."""


@dataclass(frozen=True)
class Configuration:
    """Session and Robot Configuration object class"""
    robot_address: str # IP address or URL
    labware_slots: Sequence[LabwareConfig] # Labware to use
    pipettes: Sequence[PipetteConfig] # Pipette(s) to use

    opentrons_version: OpentronsVersion = opentrons_version(2)
    custom_labware_definitions: Sequence[Path] = field(default_factory=tuple)
    python_protocol_file: Optional[Path] = None

    # Modules, perhaps?
    # …
