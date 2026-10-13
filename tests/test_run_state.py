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
