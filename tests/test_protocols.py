"""Tests for building and uploading protocols."""
import uuid

import pytest

from gdnasynth.ot2r.protocols import (Protocol, define_liquid, init_protocol,
                                      upload_protocol)
from gdnasynth.ot2r.serialization import to_jsonable


class _FakeResponse:
    """A minimal stand-in for a requests.Response."""

    def __init__(self, payload):
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


def test_upload_protocol(tmp_path):
    """Test that upload_protocol uploads the file and returns its id.

    GIVEN: a JSON protocol file and a capturing sender
    WHEN: upload_protocol(...) is called
    THEN: the file is uploaded multipart and the protocol id is returned
    """
    calls = []

    def sender(endpoint, method, data, **kwargs):
        calls.append({"endpoint": endpoint, "method": method, "data": data,
                      "kwargs": kwargs})
        return _FakeResponse(
            {"data": {"id": "11111111-1111-1111-1111-111111111111"}})

    path = tmp_path / "liquids.json"
    path.write_text("{}", encoding="utf-8")

    protocol_id = upload_protocol(sender, path)

    assert calls[-1]["endpoint"] == "/protocols"
    assert calls[-1]["method"] == "POST"
    assert calls[-1]["data"] == {"protocol_kind": "standard"}
    files = calls[-1]["kwargs"]["files"]
    assert files[0][0] == "files"
    assert files[0][1][0] == "liquids.json"
    assert files[0][1][1] == b"{}"
    assert protocol_id == uuid.UUID("11111111-1111-1111-1111-111111111111")


def test_init_protocol():
    """Test that init_protocol creates a bare protocol.

    GIVEN: a schema version and author
    WHEN: init_protocol(...) is called
    THEN: a Protocol with metadata and robot, and no liquids/commands
    """
    protocol = init_protocol(7, "tester", "My protocol")

    assert protocol.schemaVersion == 7
    assert protocol.metadata == {"protocolName": "My protocol",
                                 "author": "tester"}
    assert protocol.robot == {"model": "OT-2 Standard",
                              "deckId": "ot2_standard"}
    assert protocol.liquids == {}
    assert protocol.commands == ()


def test_init_protocol_rejects_unsupported_schema():
    """Test that init_protocol rejects an unsupported schema version.

    GIVEN: a schema version that is not supported
    WHEN: init_protocol(...) is called
    THEN: a ValueError is raised
    """
    with pytest.raises(ValueError):
        init_protocol(5, "tester")


def test_define_liquid():
    """Test that define_liquid adds a liquid definition.

    GIVEN: a protocol and a liquid definition
    WHEN: define_liquid(...) is called
    THEN: the returned protocol carries the new liquid
    """
    protocol = define_liquid(init_protocol(7, "tester"), "water-id",
                             "Water", "H2O")

    assert protocol.liquids == {
        "water-id": {"displayName": "Water", "description": "H2O"}}


def test_define_liquid_with_colour():
    """Test that define_liquid forwards an optional display colour.

    GIVEN: a protocol and a liquid definition with a colour
    WHEN: define_liquid(...) is called
    THEN: the new liquid carries the displayColor
    """
    protocol = define_liquid(init_protocol(7, "tester"), "water-id",
                             "Water", "H2O", display_color="#7332a8")

    assert protocol.liquids["water-id"]["displayColor"] == "#7332a8"


def test_define_liquid_requires_schema_6():
    """Test that define_liquid rejects a protocol too old for liquids.

    GIVEN: a protocol with schema version 5 (no liquid support)
    WHEN: define_liquid(...) is called
    THEN: a ValueError is raised
    """
    protocol = Protocol(schemaVersion=5, metadata={}, robot={})

    with pytest.raises(ValueError):
        define_liquid(protocol, "water-id", "Water", "H2O")


def test_protocol_serialises_to_json():
    """Test that a Protocol serialises to the Opentrons JSON shape.

    GIVEN: a protocol carrying a liquid
    WHEN: to_jsonable(...) is called
    THEN: the Opentrons JSON protocol representation is returned
    """
    protocol = define_liquid(init_protocol(7, "tester", "P"),
                             "water-id", "Water", "H2O")

    assert to_jsonable(protocol) == {
        "$otSharedSchema": "#/protocol/schemas/7",
        "schemaVersion": 7,
        "metadata": {"protocolName": "P", "author": "tester"},
        "robot": {"model": "OT-2 Standard", "deckId": "ot2_standard"},
        "labwareDefinitions": {},
        "commands": [],
        "liquids": {"water-id": {
            "displayName": "Water", "description": "H2O"}},
    }
