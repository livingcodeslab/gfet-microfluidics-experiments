"""Tests for protocol uploads."""
import uuid

from gdnasynth.ot2r.protocols import upload_protocol


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
