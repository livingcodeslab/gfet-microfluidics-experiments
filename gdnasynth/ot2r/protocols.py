"""Build and upload JSON protocols for the OT-2R robot."""
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from gdnasynth.ot2r.http import RequestSender
from gdnasynth.ot2r.serialization import to_jsonable


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


# The minimum protocol schema version that supports each feature.
_MIN_LIQUIDS_SCHEMA = 6

# Sections allowed by each schema version (both schemas set
# additionalProperties to false, so we must not emit unknown sections).
_ALLOWED_SECTIONS: dict[int, tuple[str, ...]] = {
    6: ("pipettes", "labwareDefinitions", "labware", "liquids", "modules",
        "commands", "commandAnnotations"),
    7: ("labwareDefinitions", "liquids", "commands", "commandAnnotations"),
}
_REQUIRED_SECTIONS: dict[int, tuple[str, ...]] = {
    6: ("pipettes", "labware", "labwareDefinitions", "commands"),
    7: ("labwareDefinitions", "commands"),
}


@dataclass(frozen=True)
class Protocol:
    """A JSON protocol for the robot."""
    schemaVersion: int
    metadata: Mapping[str, Any]
    robot: Mapping[str, str]
    pipettes: Mapping[str, Any] = field(default_factory=dict)
    labwareDefinitions: Mapping[str, Any] = field(default_factory=dict)
    labware: Mapping[str, Any] = field(default_factory=dict)
    liquids: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    modules: Mapping[str, Any] = field(default_factory=dict)
    commands: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    commandAnnotations: Sequence[Any] = field(default_factory=tuple)


@to_jsonable.register(Protocol)
def _protocol_to_json(protocol: Protocol) -> dict:
    """Serialise a Protocol to its JSON representation."""
    version = protocol.schemaVersion
    result: dict = {
        "$otSharedSchema": f"#/protocol/schemas/{version}",
        "schemaVersion": version,
        "metadata": to_jsonable(protocol.metadata),
        "robot": to_jsonable(protocol.robot),
    }
    required = _REQUIRED_SECTIONS.get(version, ())
    for section in _ALLOWED_SECTIONS.get(version, ()):
        value = getattr(protocol, section)
        if section in required or value:
            result[section] = to_jsonable(value)
    return result


def init_protocol(
        schema_version: int,
        author: str,
        protocol_name: str = "Untitled protocol",
        *,
        robot_model: str = "OT-2 Standard",
        deck_id: str = "ot2_standard"
) -> Protocol:
    """Create a bare protocol (no liquids, no commands).

    :param schema_version: The protocol schema version.
    :type schema_version: int
    :param author: The protocol's author.
    :type author: str
    :param protocol_name: The protocol's name.
    :type protocol_name: str
    :param robot_model: The robot model the protocol targets.
    :type robot_model: str
    :param deck_id: The deck the protocol targets.
    :type deck_id: str

    :rtype gdnasynth.ot2r.protocols.Protocol

    :raises ValueError: if the schema version is not supported.
    """
    if schema_version not in _ALLOWED_SECTIONS:
        raise ValueError(
            f"Unsupported protocol schema version {schema_version}; "
            f"supported: {sorted(_ALLOWED_SECTIONS)}.")
    return Protocol(
        schemaVersion=schema_version,
        metadata={"protocolName": protocol_name, "author": author},
        robot={"model": robot_model, "deckId": deck_id})


def define_liquid(
        protocol: Protocol,
        liquid_id: str,
        display_name: str,
        description: str,
        *,
        display_color: Optional[str] = None
) -> Protocol:
    """Add a liquid definition to the protocol.

    :param protocol: The protocol to add the liquid to.
    :type protocol: gdnasynth.ot2r.protocols.Protocol
    :param liquid_id: The id other commands will reference the liquid by.
    :type liquid_id: str
    :param display_name: A human-readable name for the liquid.
    :type display_name: str
    :param description: A description of the liquid.
    :type description: str
    :param display_color: An optional display colour.
    :type display_color: str, optional

    :rtype gdnasynth.ot2r.protocols.Protocol

    :raises ValueError: if the schema version does not support liquids.
    """
    if protocol.schemaVersion < _MIN_LIQUIDS_SCHEMA:
        raise ValueError(
            "Liquid definitions require protocol schema version >= "
            f"{_MIN_LIQUIDS_SCHEMA}; got {protocol.schemaVersion}.")
    liquid: dict = {"displayName": display_name, "description": description}
    if display_color is not None:
        liquid["displayColor"] = display_color
    return replace(protocol, liquids={**protocol.liquids, liquid_id: liquid})
