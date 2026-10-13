"""Tests for the protocol command helpers."""
import datetime
import uuid

from gdnasynth.ot2r.commands.runs import runs
from gdnasynth.ot2r.commands.runs.types import EngineStatus, Run, RunType
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


def _capture():
    calls = []

    def sender(endpoint, method, data, **kwargs):
        calls.append({"endpoint": endpoint, "method": method, "data": data})
        return _FakeResponse({"data": {"id": "cmd-1", "status": "queued"}})

    return sender, calls


def _pipette():
    return PipetteConfig(
        pipette_name="p20_single_gen2",
        mount="left",
        pipette_id=uuid.UUID("7806a233-8012-4d99-8887-970935f103e1"))


def _tiprack():
    return LabwareConfig(
        labware_name="opentrons_96_filtertiprack_20ul",
        load_slot=7,
        labware_id=uuid.UUID("32dbb5b7-710d-428b-bff0-03e31351e25f"))


def test_pick_up_tip():
    """Test that pick_up_tip enqueues a pickUpTip command.

    GIVEN: a pipette, a tiprack and a capturing sender
    WHEN: pick_up_tip(...) is called
    THEN: a pickUpTip command is enqueued with a protocol intent
    """
    sender, calls = _capture()

    runs.pick_up_tip(_run(), _pipette(), _tiprack(), "A1", sender)

    command = calls[-1]["data"]["data"]
    assert calls[-1]["endpoint"] == f"/maintenance_runs/{RUN_ID}/commands"
    assert calls[-1]["method"] == "POST"
    assert str(command.commandType) == "pickUpTip"
    assert command.intent == "protocol"
    assert command.params == {
        "pipetteId": "7806a233-8012-4d99-8887-970935f103e1",
        "labwareId": "32dbb5b7-710d-428b-bff0-03e31351e25f",
        "wellName": "A1",
    }


def test_aspirate():
    """Test that aspirate enqueues an aspirate command.

    GIVEN: a pipette, a reservoir and a capturing sender
    WHEN: aspirate(...) is called
    THEN: an aspirate command is enqueued with a protocol intent
    """
    sender, calls = _capture()
    reservoir = LabwareConfig(
        labware_name="nest_12_reservoir_15ml",
        load_slot=3,
        labware_id=uuid.UUID("fe305793-e2b6-40ce-94d7-2b55549b1b57"))

    runs.aspirate(_run(), _pipette(), reservoir, "A1", 10.0, 7.56, sender)

    command = calls[-1]["data"]["data"]
    assert str(command.commandType) == "aspirate"
    assert command.intent == "protocol"
    assert command.params == {
        "pipetteId": "7806a233-8012-4d99-8887-970935f103e1",
        "labwareId": "fe305793-e2b6-40ce-94d7-2b55549b1b57",
        "wellName": "A1",
        "volume": 10.0,
        "flowRate": 7.56,
    }
