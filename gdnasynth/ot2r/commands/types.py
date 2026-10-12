"""Types used in the commands."""
import uuid
import datetime
from dataclasses import field, dataclass
from typing import Any, Union, Literal, Mapping, Sequence, Optional

from gdnasynth.ot2r.commands.base_types import (NonEmptyString,
                                                NumericOpentronsVersion)
## Types encountered so far
# 1. ✔ OpentronsVersion: Literal["*", 2, 3]
# 2. ✔ DefinitionUri
# 3. ✔ AddressableAreaName
# 4. ✔ LabwareOffsetVector
# 5. ✔ LocationSequence
# 6. ✔ DeckSlotName
# 7. ✔ ModuleModel
# 8. LabwareOffsets: Sequence[Union[LegacyLabwareOffset, LabwareOffset]] = tuple()
#    a. ✔ LegacyLabwareOffset
#       - definitionUri: DefinitionUri
#       - location: LegacyLabwareOffsetLocation
#           - slotName: DeckSlotName
#           - moduleModel: Optional[ModuleModel]
#           - definitionUri: Optional[DefinitionUri]
#       - vector: LabwareOffsetVector
#    b. ✔ LabwareOffset
#       - definitionUri: DefinitionUri
#       - locationSequence: Sequence[LocationSequence]
#           - kind: Literal["onAddressableArea", "onLabware", "onModule"]
#           - addressableAreaName: AddressableAreaName
#       - vector: LabwareOffsetVector

OpentronsVersion = Union[Literal["*"], NumericOpentronsVersion]

def opentrons_version(val: Union[str, int]) -> OpentronsVersion:
    """Make an OpentronsVersiion value object.

    :param val: The value to make into an OpentronsVersion object.
    :type val: The literal '*' or integer >= 2

    :rtype gdnasynth.ot2R.commands.OpentronsVersion
    :raises ValueError"""
    if val == "*":
        return "*"
    try:
        return NumericOpentronsVersion(int(val))
    except ValueError as _verr:
        raise ValueError(
            "Invalid value! Expected either the literal '*' or an positive "
            "integer greater than or equal to 2.") from _verr


class DefinitionUri(NonEmptyString):
    """Wraps NonEmptyString to distinguish `DefinitionUri` values"""


@dataclass(frozen=True)
class LabwareOffsetVector:
    """An offset vector for labware."""
    x: float
    y: float
    z: float


LocationSequenceKind = Literal["onAddressableArea", "onLabware", "onModule"]

class AddressableAreaName(NonEmptyString):
    """Wraps NonEmptyString to distinguish `AddressableAreaName` values"""

@dataclass(frozen=True)
class LocationSequence:
    """A LocationSequence object."""
    kind: LocationSequenceKind
    addressableAreaName: AddressableAreaName


@dataclass(frozen=True)
class LabwareOffset:
    """A LabwareOffset type."""
    definitionUri: DefinitionUri
    locationSequence: Sequence[LocationSequence]
    vector: LabwareOffsetVector


DeckSlotName = Literal[
    # OT-2
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
    # Flex
    "A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3", "D1", "D2", "D3"
]


ModuleModel = Union[NonEmptyString, None]


@dataclass(frozen=True)
class LegacyLabwareOffsetLocation:
    """LegacyLabwareOffsetLocation type."""
    slotName: DeckSlotName
    moduleModel: Optional[ModuleModel]
    definitionUri: Optional[DefinitionUri]


@dataclass(frozen=True)
class LegacyLabwareOffset:
    """LegacyLabwareOffset type."""
    definitionUri: DefinitionUri
    location: LegacyLabwareOffsetLocation
    vector: LabwareOffsetVector


LabwareOffsets = Sequence[Union[LegacyLabwareOffset, LabwareOffset]]

@dataclass(frozen=True)
class LoadedLabware:
    """Labware object."""
    id: uuid.UUID
    loadName: NonEmptyString
    definitionUri: DefinitionUri
    location: dict # Locations on Opentrons devices are complex (incomplete).
    # There might be more fields defined for these types. Verify later.


@dataclass(frozen=True)
class RunError:
    """A protocol-engine error occurrence.

    Appears both as a command's ``error`` and as an entry in a run's
    ``errors`` list.  (Upstream: protocol_engine ``ErrorOccurrence``.)
    """
    id: NonEmptyString
    createdAt: datetime.datetime
    errorType: NonEmptyString
    detail: NonEmptyString
    errorCode: NonEmptyString
    isDefined: bool = False
    errorInfo: Mapping[str, Any] = field(default_factory=dict)
    wrappedErrors: Sequence['RunError'] = field(default_factory=tuple)


@dataclass(frozen=True)
class APIError:
    """A robot-server HTTP error.

    Returned in the ``errors`` list of an error response body, e.g.
    ``{"errors": [...]}``.  (Upstream: robot-server ``ErrorDetails``.)
    """
    id: NonEmptyString
    title: NonEmptyString
    detail: NonEmptyString
    errorCode: NonEmptyString
    source: Optional[dict] = None
    meta: Optional[dict] = None


CommandIntent = Literal["protocol", "setup", "fixit"]


@dataclass(frozen=True)
class Command:
    commandType: NonEmptyString # 100+ commands, Literal[...] is too verbose
    params: dict # Varies by `commandType`, no checks here for now
    intent: Optional[CommandIntent] = None   # None == server's "protocol"
    key: Optional[NonEmptyString] = None
