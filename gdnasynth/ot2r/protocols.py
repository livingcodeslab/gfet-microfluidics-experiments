"""Upload protocols to the OT-2R robot."""
import uuid
from pathlib import Path
from typing import Optional

from gdnasynth.ot2r.http import RequestSender


def _content_type(protocol_file: Path) -> str:
    """Return the MIME type to declare for the given protocol file."""
    if protocol_file.suffix == ".json":
        return "application/json"
    return "text/x-python"


def upload_protocol(
        sender: RequestSender,
        protocol_file: Path,
        key: Optional[str] = None
) -> uuid.UUID:
    """Upload a protocol file to the robot and return its protocol id.

    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender
    :param protocol_file: Path to the protocol file (JSON or Python).
    :type protocol_file: pathlib.Path
    :param key: An optional client-defined key for the protocol resource.
    :type key: str, optional

    :rtype uuid.UUID
    """
    files = [(
        "files",
        (protocol_file.name, protocol_file.read_bytes(),
         _content_type(protocol_file)))]
    data = {"protocol_kind": "standard"}
    if key is not None:
        data["key"] = key
    resp = sender(endpoint="/protocols", method="POST", data=data, files=files)
    return uuid.UUID(resp.json()["data"]["id"])
