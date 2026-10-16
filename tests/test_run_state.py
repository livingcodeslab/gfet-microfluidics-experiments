"""Tests for the run-state helpers."""
import datetime
import uuid

from gdnasynth.ot2r.commands.runs import runs
from gdnasynth.ot2r.commands.runs.types import EngineStatus, Run, RunType

RUN_ID = "4023a0e2-d70d-4f6e-91f7-9808dd170273"

RUN_PAYLOAD = {
    "id": RUN_ID,
    "createdAt": "2026-09-15T15:14:35.049438Z",
    "status": "idle",
    "current": True,
    "actions": [],
    "errors": [],
    "hasEverEnteredErrorRecovery": False,
    "pipettes": [],
    "modules": [],
    "labware": [],
    "liquids": [],
    "liquidClasses": [],
    "labwareOffsets": [],
}


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


def _capture(payload):
    calls = []

    def sender(endpoint, method, data, **kwargs):
        calls.append({"endpoint": endpoint, "method": method, "data": data})
        return _FakeResponse(payload)

    return sender, calls


def test_get_run():
    """Test that get_run fetches and parses a run by id.

    GIVEN: a run payload and a capturing sender
    WHEN: get_run(...) is called
    THEN: the run is GET from its endpoint and parsed
    """
    sender, calls = _capture({"data": RUN_PAYLOAD})

    run = runs.get_run(sender, RunType.MAINTENANCERUN, uuid.UUID(RUN_ID))

    assert calls[-1]["endpoint"] == f"/maintenance_runs/{RUN_ID}"
    assert calls[-1]["method"] == "GET"
    assert run.id == uuid.UUID(RUN_ID)
    assert run.status == EngineStatus.IDLE


def test_get_current_run():
    """Test that get_current_run fetches and parses the current run.

    GIVEN: a run payload and a capturing sender
    WHEN: get_current_run(...) is called
    THEN: the current run is GET from its endpoint and parsed
    """
    sender, calls = _capture({"data": RUN_PAYLOAD})

    run = runs.get_current_run(sender, RunType.MAINTENANCERUN)

    assert calls[-1]["endpoint"] == "/maintenance_runs/current_run"
    assert calls[-1]["method"] == "GET"
    assert run.id == uuid.UUID(RUN_ID)


def test_delete_run():
    """Test that delete_run deletes a run.

    GIVEN: a run and a capturing sender
    WHEN: delete_run(...) is called
    THEN: the run is DELETEd from its endpoint
    """
    sender, calls = _capture({})

    runs.delete_run(sender, _run())

    assert calls[-1]["endpoint"] == f"/maintenance_runs/{RUN_ID}"
    assert calls[-1]["method"] == "DELETE"


def test_list_commands():
    """Test that list_commands fetches a run's commands.

    GIVEN: a commands payload and a capturing sender
    WHEN: list_commands(...) is called
    THEN: the commands are GET from the run's commands endpoint
    """
    commands = [
        {"id": "cmd-1", "commandType": "loadLabware", "status": "succeeded"},
    ]
    sender, calls = _capture({"data": commands})

    result = runs.list_commands(sender, _run())

    assert calls[-1]["endpoint"] == f"/maintenance_runs/{RUN_ID}/commands"
    assert calls[-1]["method"] == "GET"
    assert result == commands


def test_get_command():
    """Test that get_command fetches a single command by id.

    GIVEN: a command payload and a capturing sender
    WHEN: get_command(...) is called
    THEN: the command is GET from its endpoint and returned raw
    """
    command = {
        "id": "ccd9b2d0-064f-41d7-b0c7-d0df60bb1124",
        "commandType": "loadLabware",
        "status": "succeeded",
    }
    sender, calls = _capture({"data": command})

    result = runs.get_command(
        sender, _run(),
        uuid.UUID("ccd9b2d0-064f-41d7-b0c7-d0df60bb1124"))

    assert calls[-1]["endpoint"] == (
        f"/maintenance_runs/{RUN_ID}/commands/"
        "ccd9b2d0-064f-41d7-b0c7-d0df60bb1124")
    assert calls[-1]["method"] == "GET"
    assert result == command


def test_create_run_with_protocol_id():
    """Test that create_run forwards a protocolId when one is given.

    GIVEN: a run payload and a capturing sender
    WHEN: create_run(...) is called with a protocol_id
    THEN: the normal run create body carries that protocolId
    """
    sender, calls = _capture({"data": RUN_PAYLOAD})

    run = runs.create_run(
        sender, RunType.NORMALRUN, (),
        protocol_id=uuid.UUID("22222222-2222-2222-2222-222222222222"))

    assert calls[-1]["endpoint"] == "/runs"
    assert calls[-1]["method"] == "POST"
    assert calls[-1]["data"] == {"data": {
        "labwareOffsets": (),
        "protocolId": "22222222-2222-2222-2222-222222222222",
    }}
    assert run.id == uuid.UUID(RUN_ID)


def test_create_run_without_protocol_id():
    """Test that create_run omits protocolId when none is given.

    GIVEN: a run payload and a capturing sender
    WHEN: create_run(...) is called without a protocol_id
    THEN: the create body carries only the labware offsets
    """
    sender, calls = _capture({"data": RUN_PAYLOAD})

    runs.create_run(sender, RunType.MAINTENANCERUN, ())

    assert calls[-1]["data"] == {"data": {"labwareOffsets": ()}}


def test_play():
    """Test that play posts a play action for the run.

    GIVEN: a run and a capturing sender
    WHEN: play(...) is called
    THEN: a 'play' action is POSTed to the run's actions endpoint
    """
    sender, calls = _capture(
        {"data": {"id": "act-1", "actionType": "play"}})

    result = runs.play(sender, _run())

    assert calls[-1]["endpoint"] == f"/maintenance_runs/{RUN_ID}/actions"
    assert calls[-1]["method"] == "POST"
    assert calls[-1]["data"] == {"data": {"actionType": "play"}}
    assert result == {"id": "act-1", "actionType": "play"}


def test_pause():
    """Test that pause posts a pause action for the run.

    GIVEN: a run and a capturing sender
    WHEN: pause(...) is called
    THEN: a 'pause' action is POSTed to the run's actions endpoint
    """
    sender, calls = _capture(
        {"data": {"id": "act-2", "actionType": "pause"}})

    result = runs.pause(sender, _run())

    assert calls[-1]["endpoint"] == f"/maintenance_runs/{RUN_ID}/actions"
    assert calls[-1]["method"] == "POST"
    assert calls[-1]["data"] == {"data": {"actionType": "pause"}}
    assert result == {"id": "act-2", "actionType": "pause"}
