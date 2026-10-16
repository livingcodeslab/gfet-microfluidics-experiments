"""Tests for `send_request`: serialisation and error handling."""
import datetime
import json
import uuid

import pytest
import requests

from gdnasynth.ot2r import http
from gdnasynth.ot2r.commands.base_types import NonEmptyString


class _FakeResponse:
    """A minimal stand-in for a requests.Response."""

    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON body")
        return self._payload


def test_send_request_serialises_payload(monkeypatch):
    """Test that custom objects reach requests as JSON primitives.

    GIVEN: a payload carrying uuid.UUID, NonEmptyString, datetime, and a
           tuple value
    WHEN: send_request(...) is called
    THEN: the value handed to requests is JSON-ready primitives
    """
    recorded = {}

    def fake_post(url, **kwargs):
        recorded["url"] = url
        recorded["kwargs"] = kwargs
        return _FakeResponse(payload={"data": {}})

    monkeypatch.setattr(http.requests, "post", fake_post)

    when = datetime.datetime(2026, 9, 15, 15, 14, 35,
                             tzinfo=datetime.timezone.utc)
    payload = {
        "data": {
            "id": uuid.UUID("c9c762e1-8205-4ccd-be32-6535fd0e9514"),
            "name": NonEmptyString("x"),
            "when": when,
            "items": (1, 2),
        }
    }

    http.send_request("http://robot:31950", "/maintenance_runs", "POST",
                      "*", payload)

    assert recorded["url"] == "http://robot:31950/maintenance_runs"
    assert recorded["kwargs"]["json"] == {
        "data": {
            "id": "c9c762e1-8205-4ccd-be32-6535fd0e9514",
            "name": "x",
            "when": "2026-09-15T15:14:35+00:00",
            "items": [1, 2],
        }
    }


def test_send_request_wraps_connection_errors(monkeypatch):
    """Test that connection failures raise RobotUnreachable.

    GIVEN: requests raises a ConnectionError
    WHEN: send_request(...) is called
    THEN: a RobotUnreachable error is raised
    """
    def fake_post(url, **kwargs):
        raise requests.exceptions.ConnectionError("No route to host")

    monkeypatch.setattr(http.requests, "post", fake_post)

    with pytest.raises(http.RobotUnreachable):
        http.send_request("http://robot:31950", "/maintenance_runs",
                          "POST", "*", {})


def test_send_request_raises_on_http_error(monkeypatch):
    """Test that non-2xx responses raise RobotResponseError.

    GIVEN: the robot returns 502 with a non-JSON body
    WHEN: send_request(...) is called
    THEN: RobotResponseError carries the status and body
    """
    body = "<html><head><title>502 Bad Gateway</title></head></html>"

    def fake_post(url, **kwargs):
        return _FakeResponse(status_code=502, text=body)

    monkeypatch.setattr(http.requests, "post", fake_post)

    with pytest.raises(http.RobotResponseError) as excinfo:
        http.send_request("http://robot:31950", "/maintenance_runs",
                          "POST", "*", {})

    assert excinfo.value.status_code == 502
    assert excinfo.value.body == body
    assert excinfo.value.api_errors == ()


def test_send_request_parses_api_error_envelope(monkeypatch):
    """Test that the {"errors": [...]} envelope is parsed.

    GIVEN: the robot returns 400 with an API error envelope
    WHEN: send_request(...) is called
    THEN: RobotResponseError carries the parsed APIError objects
    """
    payload = {"errors": [{
        "id": "HardwareNotYetInitialized",
        "title": "Hardware Not Yet Initialized",
        "detail": "The device's hardware has not finished initializing.",
        "errorCode": "4000",
    }]}

    def fake_post(url, **kwargs):
        return _FakeResponse(payload=payload, status_code=400,
                             text=json.dumps(payload))

    monkeypatch.setattr(http.requests, "post", fake_post)

    with pytest.raises(http.RobotResponseError) as excinfo:
        http.send_request("http://robot:31950", "/maintenance_runs",
                          "POST", "*", {})

    api_errors = excinfo.value.api_errors
    assert len(api_errors) == 1
    assert str(api_errors[0].id) == "HardwareNotYetInitialized"
    assert str(api_errors[0].title) == "Hardware Not Yet Initialized"
    assert str(api_errors[0].errorCode) == "4000"


def test_send_request_returns_response_on_success(monkeypatch):
    """Test that a successful response is returned unchanged.

    GIVEN: the robot returns 201
    WHEN: send_request(...) is called
    THEN: the response is returned
    """
    def fake_post(url, **kwargs):
        return _FakeResponse(payload={"data": {}}, status_code=201)

    monkeypatch.setattr(http.requests, "post", fake_post)

    response = http.send_request("http://robot:31950", "/maintenance_runs",
                                 "POST", "*", {})

    assert response.status_code == 201


def test_send_request_sends_files_as_multipart(monkeypatch):
    """Test that a `files` payload is sent as multipart form data.

    GIVEN: a request carrying files (and form fields)
    WHEN: send_request(...) is called
    THEN: requests receives the files and form fields, with no JSON body
    """
    recorded = {}

    def fake_post(url, **kwargs):
        recorded["url"] = url
        recorded["kwargs"] = kwargs
        return _FakeResponse(payload={"data": {}})

    monkeypatch.setattr(http.requests, "post", fake_post)

    files = [("files", ("protocol.json", b"{}", "application/json"))]
    http.send_request("http://robot:31950", "/protocols", "POST", "*",
                      {"protocol_kind": "standard"}, files=files)

    assert recorded["url"] == "http://robot:31950/protocols"
    assert recorded["kwargs"]["files"] == files
    assert recorded["kwargs"]["data"] == {"protocol_kind": "standard"}
    assert "json" not in recorded["kwargs"]
    assert "Content-Type" not in recorded["kwargs"]["headers"]
