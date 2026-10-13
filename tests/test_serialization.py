"""Tests for `gdnasynth.ot2r.serialization.to_jsonable`.

`to_jsonable` is recursive: it should turn any of our types into plain JSON
primitives (dict/list/str/int/float/bool/None), ready for `json.dumps`.

These tests are written before the implementation, so they fail at
collection (missing module) until `gdnasynth.ot2r.serialization` lands.
Run with:  python3 -m pytest tests/test_serialization.py
"""
import dataclasses
import datetime
import enum
import json
import uuid
from typing import Optional

import pytest

from gdnasynth.ot2r.serialization import to_jsonable
from gdnasynth.ot2r.commands.base_types import NonEmptyString
from gdnasynth.ot2r.commands.types import (AddressableAreaName,
                                           Command,
                                           DefinitionUri,
                                           LoadedLabware)
from gdnasynth.ot2r.commands.runs.types import (EngineStatus,
                                                Run,
                                                RunType)

UUID_STR = "c9c762e1-8205-4ccd-be32-6535fd0e9514"
UUID_VAL = uuid.UUID(UUID_STR)
WHEN = datetime.datetime(2026, 9, 15, 15, 14, 35, 49438,
                         tzinfo=datetime.timezone.utc)
WHEN_STR = "2026-09-15T15:14:35.049438+00:00"


class Colour(enum.Enum):
    """An arbitrary enum for the generic conversion test."""

    RED = "red"


@dataclasses.dataclass(frozen=True)
class Flat:
    """A minimal dataclass."""

    a: int
    b: str


@dataclasses.dataclass(frozen=True)
class Nested:
    """A dataclass exercising nesting, custom types, and a None field."""

    name: NonEmptyString
    when: datetime.datetime
    identifier: uuid.UUID
    inner: Flat
    tags: tuple
    extra: dict
    missing: Optional[str] = None


@pytest.mark.parametrize("value", [None, True, False, 0, 1, -3, 1.5, 0.0, "", "abc"])
def test_primitives_pass_through(value):
    """Test that primitive Python types pass through the serializer.

    GIVEN: a primitive python type, e.g. int, string, float, NoneType, etc
    WHEN: it's passed to the `to_jsonable(...)` serializer as the value
    THEN: return the value unchanged.
    """
    assert to_jsonable(value) == value


@pytest.mark.parametrize("value, expected", [
    (WHEN, WHEN_STR),
    (datetime.datetime(2026, 9, 15, 15, 14, 35), "2026-09-15T15:14:35"),
])
def test_datetime_to_isoformat(value, expected):
    """Test that datetime.datetime values are serialised to their ISO format

    GIVEN: a datetime.datetime object
    WHEN: it's passed to the `to_jsonable(...)` serializer as the value
    THEN: return the ISO format representation of the object
    """
    assert to_jsonable(value) == expected


def test_uuid_to_str():
    """Test that uuid.UUID values are serialised to their string representation.

    GIVEN: a uuid.UUID object
    WHEN: it's passed to the `to_jsonable(...)` serializer as the value
    THEN: return the string representation of the UUID value
    """
    assert to_jsonable(UUID_VAL) == UUID_STR


@pytest.mark.parametrize("value, expected", [
    (NonEmptyString("hello"), "hello"),
    (DefinitionUri("ns/load/1"), "ns/load/1"),
    (AddressableAreaName("A1"), "A1"),
])
def test_nonempty_string_to_str(value, expected):
    """Test that NonEmptyString values serialise to their string form.

    GIVEN: a NonEmptyString, or one of its subclasses (DefinitionUri,
           AddressableAreaName)
    WHEN: it's passed to the `to_jsonable(...)` serializer as the value
    THEN: return the string representation of the value
    """
    assert to_jsonable(value) == expected


def test_enum_to_value():
    """Test that enum members serialise to their values.

    GIVEN: an enum.Enum member
    WHEN: it's passed to the `to_jsonable(...)` serializer as the value
    THEN: return the member's value
    """
    assert to_jsonable(Colour.RED) == "red"


@pytest.mark.parametrize("value, expected", [
    ([1, "a", None], [1, "a", None]),
    ((1, "a", None), [1, "a", None]),
])
def test_sequence_to_list(value, expected):
    """Test that sequences serialise to JSON arrays.

    GIVEN: a list or tuple
    WHEN: it's passed to the `to_jsonable(...)` serializer as the value
    THEN: return a list of the serialised items
    """
    assert to_jsonable(value) == expected


def test_dict_values_are_converted_recursively():
    """Test that mapping values are converted recursively.

    GIVEN: a dict whose values include custom types and nested containers
    WHEN: it's passed to the `to_jsonable(...)` serializer as the value
    THEN: return a dict with every value serialised in turn
    """
    value = {"u": UUID_VAL, "n": NonEmptyString("x"), "nested": {"t": (1, 2)}}
    assert to_jsonable(value) == {
        "u": UUID_STR, "n": "x", "nested": {"t": [1, 2]}}


@pytest.mark.parametrize("value, expected", [
    (Flat(a=1, b="x"), {"a": 1, "b": "x"}),
    (Nested(name=NonEmptyString("n"), when=WHEN, identifier=UUID_VAL,
            inner=Flat(1, "b"), tags=(1, 2), extra={"k": "v"}),
     {"name": "n", "when": WHEN_STR, "identifier": UUID_STR,
      "inner": {"a": 1, "b": "b"}, "tags": [1, 2], "extra": {"k": "v"},
      "missing": None}),
])
def test_dataclass_to_dict(value, expected):
    """Test that dataclasses serialise to dicts, recursively.

    GIVEN: a (possibly nested) dataclass instance, including None fields
    WHEN: it's passed to the `to_jsonable(...)` serializer as the value
    THEN: return a dict of its fields, each serialised in turn
    """
    assert to_jsonable(value) == expected


def test_command():
    """Test that a Command serialises to its JSON payload.

    GIVEN: a Command with a commandType and params
    WHEN: it's passed to the `to_jsonable(...)` serializer as the value
    THEN: return a dict of the command's fields, with unset optionals as None
    """
    command = Command(commandType=NonEmptyString("loadLabware"),
                      params={"location": {"slotName": "1"}})
    assert to_jsonable(command) == {
        "commandType": "loadLabware",
        "params": {"location": {"slotName": "1"}},
        "intent": None,
        "key": None,
    }


def test_loaded_labware():
    """Test that a LoadedLabware serialises to its JSON payload.

    GIVEN: a LoadedLabware, with its location left as a raw dict
    WHEN: it's passed to the `to_jsonable(...)` serializer as the value
    THEN: return a dict of its fields, with custom types as strings
    """
    labware = LoadedLabware(
        id=uuid.UUID("32dbb5b7-710d-428b-bff0-03e31351e25f"),
        loadName=NonEmptyString("opentrons_96_filtertiprack_20ul"),
        definitionUri=DefinitionUri(
            "opentrons/opentrons_96_filtertiprack_20ul/1"),
        location={"slotName": "7"})
    assert to_jsonable(labware) == {
        "id": "32dbb5b7-710d-428b-bff0-03e31351e25f",
        "loadName": "opentrons_96_filtertiprack_20ul",
        "definitionUri": "opentrons/opentrons_96_filtertiprack_20ul/1",
        "location": {"slotName": "7"},
    }


def test_run():
    """Test that a Run serialises to its JSON payload.

    GIVEN: a Run carrying enum, datetime, and UUID values
    WHEN: it's passed to the `to_jsonable(...)` serializer as the value
    THEN: return a dict with each field serialised appropriately
    """
    run = Run(runType=RunType.MAINTENANCERUN, id=UUID_VAL,
              createdAt=WHEN, status=EngineStatus.IDLE)
    result = to_jsonable(run)
    assert result["runType"] == "maintenance_run"
    assert result["id"] == UUID_STR
    assert result["createdAt"] == WHEN_STR
    assert result["status"] == "idle"
    assert result["labware"] == []


def test_result_is_json_serialisable():
    """Test that the serialised output is json.dumps-able.

    GIVEN: a Command with its optional fields set
    WHEN: its serialised form is passed to `json.dumps(...)`
    THEN: no exception is raised
    """
    command = Command(commandType=NonEmptyString("home"), params={},
                      intent="protocol", key=NonEmptyString("k"))
    json.dumps(to_jsonable(command))  # must not raise


def test_unsupported_type_raises():
    """Test that unsupported types are rejected.

    GIVEN: an object of a type the serializer does not handle
    WHEN: it's passed to the `to_jsonable(...)` serializer as the value
    THEN: raise a TypeError
    """
    with pytest.raises(TypeError):
        to_jsonable(object())
