"""Tests for the serialisation boundary in `send_request`."""
import datetime
import uuid

from gdnasynth.ot2r import http
from gdnasynth.ot2r.commands.base_types import NonEmptyString


class _FakeResponse:
    """A minimal stand-in for a requests.Response."""


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
        return _FakeResponse()

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
