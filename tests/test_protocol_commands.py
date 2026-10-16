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

    runs.pick_up_tip(sender, _run(), _pipette(), _tiprack(), "A1")

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

    runs.aspirate(sender, _run(), _pipette(), reservoir, "A1",
                  10.0, 7.56)

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


def test_dispense():
    """Test that dispense enqueues a dispense command.

    GIVEN: a pipette, a chip and a capturing sender
    WHEN: dispense(...) is called
    THEN: a dispense command is enqueued with a protocol intent
    """
    sender, calls = _capture()
    chip = LabwareConfig(
        labware_name="livingcodeslab_graphenea_card_adapter",
        load_slot=1,
        labware_id=uuid.UUID("c9c762e1-8205-4ccd-be32-6535fd0e9514"),
        namespace="livingcodeslab")

    runs.dispense(sender, _run(), _pipette(), chip, "A1",
                  10.0, 7.56)

    command = calls[-1]["data"]["data"]
    assert str(command.commandType) == "dispense"
    assert command.intent == "protocol"
    assert command.params == {
        "pipetteId": "7806a233-8012-4d99-8887-970935f103e1",
        "labwareId": "c9c762e1-8205-4ccd-be32-6535fd0e9514",
        "wellName": "A1",
        "volume": 10.0,
        "flowRate": 7.56,
    }


def test_drop_tip():
    """Test that drop_tip enqueues a dropTip command.

    GIVEN: a pipette, a tiprack and a capturing sender
    WHEN: drop_tip(...) is called
    THEN: a dropTip command is enqueued with a protocol intent
    """
    sender, calls = _capture()

    runs.drop_tip(sender, _run(), _pipette(), _tiprack(), "A1")

    command = calls[-1]["data"]["data"]
    assert str(command.commandType) == "dropTip"
    assert command.intent == "protocol"
    assert command.params == {
        "pipetteId": "7806a233-8012-4d99-8887-970935f103e1",
        "labwareId": "32dbb5b7-710d-428b-bff0-03e31351e25f",
        "wellName": "A1",
    }


def test_home():
    """Test that home enqueues a home command.

    GIVEN: a capturing sender
    WHEN: home(...) is called
    THEN: a home command is enqueued with a protocol intent
    """
    sender, calls = _capture()

    runs.home(sender, _run())

    command = calls[-1]["data"]["data"]
    assert str(command.commandType) == "home"
    assert command.intent == "protocol"
    assert command.params == {}


def test_trash_tip():
    """Test that trash_tip moves to the trash and drops the tip.

    GIVEN: a pipette and a capturing sender
    WHEN: trash_tip(...) is called
    THEN: moveToAddressableAreaForDropTip and dropTipInPlace are enqueued
    """
    sender, calls = _capture()

    result = runs.trash_tip(sender, _run(), _pipette())

    move = calls[-2]["data"]["data"]
    drop = calls[-1]["data"]["data"]
    assert calls[-2]["endpoint"] == f"/maintenance_runs/{RUN_ID}/commands"
    assert str(move.commandType) == "moveToAddressableAreaForDropTip"
    assert move.intent == "protocol"
    assert move.params == {
        "pipetteId": "7806a233-8012-4d99-8887-970935f103e1",
        "addressableAreaName": "fixedTrash",
    }
    assert str(drop.commandType) == "dropTipInPlace"
    assert drop.intent == "protocol"
    assert drop.params == {
        "pipetteId": "7806a233-8012-4d99-8887-970935f103e1",
    }
    assert len(result) == 2


def test_aspirate_with_well_location():
    """Test that aspirate forwards a wellLocation when one is given.

    GIVEN: a pipette, a reservoir, and a well location
    WHEN: aspirate(...) is called with well_location
    THEN: the aspirate command carries that wellLocation
    """
    sender, calls = _capture()
    reservoir = LabwareConfig(
        labware_name="nest_12_reservoir_15ml",
        load_slot=3,
        labware_id=uuid.UUID("fe305793-e2b6-40ce-94d7-2b55549b1b57"))

    runs.aspirate(sender, _run(), _pipette(), reservoir, "A1", 10.0, 7.56,
                  well_location={"origin": "center"})

    command = calls[-1]["data"]["data"]
    assert command.params == {
        "pipetteId": "7806a233-8012-4d99-8887-970935f103e1",
        "labwareId": "fe305793-e2b6-40ce-94d7-2b55549b1b57",
        "wellName": "A1",
        "volume": 10.0,
        "flowRate": 7.56,
        "wellLocation": {"origin": "center"},
    }


def test_dispense_with_well_location():
    """Test that dispense forwards a wellLocation when one is given.

    GIVEN: a pipette, a chip, and a well location
    WHEN: dispense(...) is called with well_location
    THEN: the dispense command carries that wellLocation
    """
    sender, calls = _capture()
    chip = LabwareConfig(
        labware_name="livingcodeslab_graphenea_card_adapter",
        load_slot=1,
        labware_id=uuid.UUID("c9c762e1-8205-4ccd-be32-6535fd0e9514"),
        namespace="livingcodeslab")

    runs.dispense(sender, _run(), _pipette(), chip, "A1", 10.0, 7.56,
                  well_location={"origin": "bottom"})

    command = calls[-1]["data"]["data"]
    assert command.params == {
        "pipetteId": "7806a233-8012-4d99-8887-970935f103e1",
        "labwareId": "c9c762e1-8205-4ccd-be32-6535fd0e9514",
        "wellName": "A1",
        "volume": 10.0,
        "flowRate": 7.56,
        "wellLocation": {"origin": "bottom"},
    }
