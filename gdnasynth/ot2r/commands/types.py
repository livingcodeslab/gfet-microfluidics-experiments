"""Types used in the commands."""
from dataclasses import dataclass
from typing import Union, Literal, Sequence, Optional

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
