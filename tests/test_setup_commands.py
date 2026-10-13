"""Tests for the setup helpers add_labware_definition / load_labware /
load_pipette."""
import datetime
import json
import uuid

from gdnasynth.ot2r.commands.runs.runs import (add_labware_definition,
                                               load_labware,
                                               load_pipette)
from gdnasynth.ot2r.commands.runs.types import EngineStatus, Run, RunType
from gdnasynth.ot2r.commands.types import DefinitionUri
from gdnasynth.ot2r.types import LabwareConfig, PipetteConfig

RUN_ID = "4023a0e2-d70d-4f6e-91f7-9808dd170273"


class _FakeResponse:
    """A minimal stand-in for a requests.Response."""

    def __init__(self, payload):
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


def _run():
    return Run(runType=RunType.MAINTENANCERUN, id=uuid.UUID(RUN_ID),
               createdAt=datetime.datetime(2026, 9, 15),
               status=EngineStatus.IDLE)


def _capture(payload=None):
    calls = []

    def sender(endpoint, method, data, **kwargs):
        calls.append({"endpoint": endpoint, "method": method, "data": data})
        return _FakeResponse(
            payload if payload is not None
            else {"data": {"id": "cmd-1", "status": "queued"}})

    return sender, calls


def test_add_labware_definition(tmp_path):
    """Test that add_labware_definition uploads a definition file.

    GIVEN: a labware definition JSON file and a capturing sender
    WHEN: add_labware_definition(...) is called
    THEN: the definition is POSTed and its DefinitionUri is returned
    """
    definition = {
        "ordering": [],
        "brand": {"brand": "livingcodeslab"},
        "metadata": {"displayName": "Graphenea card adapter"},
    }
    path = tmp_path / "definition.json"
    path.write_text(json.dumps(definition), encoding="utf-8")

    sender, calls = _capture({
        "data": {"definitionUri":
                 "livingcodeslab/livingcodeslab_graphenea_card_adapter/1"}})

    uri = add_labware_definition(sender, _run(), path)

    assert calls[-1]["endpoint"] == (
        f"/maintenance_runs/{RUN_ID}/labware_definitions")
    assert calls[-1]["method"] == "POST"
    assert calls[-1]["data"] == {"data": definition}
    assert isinstance(uri, DefinitionUri)
    assert str(uri) == (
        "livingcodeslab/livingcodeslab_graphenea_card_adapter/1")


def test_load_labware():
    """Test that load_labware enqueues a loadLabware command.

    GIVEN: a LabwareConfig and a capturing sender
    WHEN: load_labware(...) is called
    THEN: a loadLabware command is enqueued with the labware's parameters
    """
    sender, calls = _capture()
    labware = LabwareConfig(
        labware_name="opentrons_96_filtertiprack_20ul",
        load_slot=7,
        labware_id=uuid.UUID("32dbb5b7-710d-428b-bff0-03e31351e25f"),
        namespace="opentrons")

    load_labware(sender, _run(), labware)

    command = calls[-1]["data"]["data"]
    assert calls[-1]["endpoint"] == f"/maintenance_runs/{RUN_ID}/commands"
    assert calls[-1]["method"] == "POST"
    assert str(command.commandType) == "loadLabware"
    assert command.intent == "setup"
    assert command.params == {
        "location": {"slotName": "7"},
        "loadName": "opentrons_96_filtertiprack_20ul",
        "namespace": "opentrons",
        "version": 1,
        "labwareId": "32dbb5b7-710d-428b-bff0-03e31351e25f",
    }


def test_load_pipette():
    """Test that load_pipette enqueues a loadPipette command.

    GIVEN: a PipetteConfig and a capturing sender
    WHEN: load_pipette(...) is called
    THEN: a loadPipette command is enqueued with the pipette's parameters
    """
    sender, calls = _capture()
    pipette = PipetteConfig(
        pipette_name="p20_single_gen2",
        mount="left",
        pipette_id=uuid.UUID("7806a233-8012-4d99-8887-970935f103e1"))

    load_pipette(sender, _run(), pipette)

    command = calls[-1]["data"]["data"]
    assert calls[-1]["endpoint"] == f"/maintenance_runs/{RUN_ID}/commands"
    assert calls[-1]["method"] == "POST"
    assert str(command.commandType) == "loadPipette"
    assert command.intent == "setup"
    assert command.params == {
        "pipetteName": "p20_single_gen2",
        "mount": "left",
        "pipetteId": "7806a233-8012-4d99-8887-970935f103e1",
    }
