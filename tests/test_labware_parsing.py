"""Tests for parsing a run's labware."""
import uuid

import pytest

from gdnasynth.ot2r.commands.base_types import NonEmptyString
from gdnasynth.ot2r.commands.runs.runs import parse_labware


def test_parse_labware_with_uuid_id():
    """Test that a UUID labware id is parsed to a uuid.UUID.

    GIVEN: a labware entry with a UUID id
    WHEN: parse_labware(...) is called
    THEN: the LoadedLabware id is a uuid.UUID
    """
    result = parse_labware([{
        "id": "32dbb5b7-710d-428b-bff0-03e31351e25f",
        "loadName": "opentrons_96_filtertiprack_20ul",
        "definitionUri": "opentrons/opentrons_96_filtertiprack_20ul/1",
        "location": {"slotName": "7"},
    }])

    assert result[0].id == uuid.UUID("32dbb5b7-710d-428b-bff0-03e31351e25f")


def test_parse_labware_with_non_uuid_id():
    """Test that a non-UUID labware id is parsed to a NonEmptyString.

    GIVEN: a labware entry whose id is a name (e.g. the fixed trash)
    WHEN: parse_labware(...) is called
    THEN: the LoadedLabware id is a NonEmptyString
    """
    result = parse_labware([{
        "id": "fixedTrash",
        "loadName": "opentrons_1_trash_1100ml_fixed",
        "definitionUri": "opentrons/opentrons_1_trash_1100ml_fixed/1",
        "location": {"slotName": "12"},
    }])

    assert str(result[0].id) == "fixedTrash"


def test_parse_labware_rejects_empty_id():
    """Test that an empty labware id is rejected.

    GIVEN: a labware entry with an empty id
    WHEN: parse_labware(...) is called
    THEN: a ValueError is raised
    """
    with pytest.raises(ValueError):
        parse_labware([{
            "id": "",
            "loadName": "some_labware",
            "definitionUri": "opentrons/some_labware/1",
            "location": {"slotName": "1"},
        }])
