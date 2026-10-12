"""Commands concerning runs."""
import json
import uuid
import datetime
from pathlib import Path
from typing import Sequence, Union

from gdnasynth.ot2r.http import RequestSender
from gdnasynth.ot2r.commands.base_types import NonEmptyString
from gdnasynth.ot2r.commands.types import (Command,
                                           DefinitionUri,
                                           LabwareOffset,
                                           LabwareOffsets,
                                           LocationSequence,
                                           AddressableAreaName,
                                           LabwareOffsetVector,
                                           LegacyLabwareOffset,
                                           LegacyLabwareOffsetLocation,
                                           LoadedLabware)

from .types import Run, RunType, EngineStatus

## Notes:
# Difference between normal runs and  maintenance runs are:
# 1. endpoints: /runs vs. /maintenance_runs
# 2. Normal runs need you to trigger 'play', maintenance runs don't


## Steps involved in a maintenance run
#
# 1. Create/Register a run ==> create_run(offsets: LabwareOffsets)

def parse_status(val: str) -> EngineStatus:
    """Parse the value into a valid EngineStatus"""
    return {status.value: status for status in EngineStatus}[val]


def parse_labware_offset_vector(data: dict) -> LabwareOffsetVector:
    """Parse a single labware offset vector from the robot's response."""
    return LabwareOffsetVector(x=data["x"], y=data["y"], z=data["z"])


def parse_location_sequence(data: dict) -> LocationSequence:
    """Parse a single location-sequence component from the robot's response.

    The robot can return three kinds of component:

    - ``onAddressableArea`` with an ``addressableAreaName``;
    - ``onModule`` with a ``moduleModel``;
    - ``onLabware`` with a ``labwareUri``.

    The current ``LocationSequence`` type only models the first, so the
    other two raise.  See the recommended type fix accompanying this
    parser.
    """
    if data["kind"] != "onAddressableArea":
        raise ValueError(
            "Unsupported location-sequence component kind "
            f"{data['kind']!r}: the LocationSequence type models only "
            "'onAddressableArea' components.")
    return LocationSequence(
        kind="onAddressableArea",
        addressableAreaName=AddressableAreaName(data["addressableAreaName"]))


def parse_labware_offset(data: dict) -> Union[LegacyLabwareOffset, LabwareOffset]:
    """Parse a single labware offset from the robot's response.

    Every offset the robot returns carries a (deprecated) legacy
    ``location``; newer runs additionally carry a ``locationSequence``.
    When the sequence is present we build a ``LabwareOffset``, otherwise
    a ``LegacyLabwareOffset``.
    """
    vector = parse_labware_offset_vector(data["vector"])
    definition_uri = DefinitionUri(data["definitionUri"])
    location_sequence = data.get("locationSequence")
    if location_sequence is not None:
        return LabwareOffset(
            definitionUri=definition_uri,
            locationSequence=tuple(
                parse_location_sequence(component)
                for component in location_sequence),
            vector=vector)

    location = data["location"]
    return LegacyLabwareOffset(
        definitionUri=definition_uri,
        location=LegacyLabwareOffsetLocation(
            slotName=location["slotName"],
            moduleModel=(
                NonEmptyString(location["moduleModel"])
                if location.get("moduleModel") is not None else None),
            definitionUri=(
                DefinitionUri(location["definitionUri"])
                if location.get("definitionUri") is not None else None)),
        vector=vector)


def parse_labware_offsets(data: Sequence[dict]) -> LabwareOffsets:
    """Parse the ``labwareOffsets`` list from a run response."""
    return tuple(parse_labware_offset(offset) for offset in data)


def parse_labware(data: Sequence[dict]) -> Sequence[LoadedLabware]:
    """Parse the ``labware`` list from a run response.

    The labware ``location`` is kept as a raw ``dict`` for now: Opentrons
    locations are a complex union that we have not modelled yet.
    """
    return tuple(
        LoadedLabware(
            id=uuid.UUID(labware["id"]),
            loadName=NonEmptyString(labware["loadName"]),
            definitionUri=DefinitionUri(labware["definitionUri"]),
            location=labware["location"])
        for labware in data)


def parse_run_result(result: dict, runtype: RunType) -> Run:
    """Parse the response json."""
    return Run(**{
        "runType": runtype,
        **result,
        "id": uuid.UUID(result["id"]),
        "createdAt": datetime.datetime.fromisoformat(result["createdAt"]),
        "status": parse_status(result["status"]),
        # "actions": parse_run_actions(result["actions"]),
        # "errors": parse_run_errors(result["errors"]),
        # "pipettes": parse_pipettes(result["pipettes"]),
        # "modules": parse_modules(result["pipettes"]),
        "labware": parse_labware(result["labware"]),
        # "liquids": parse_liquids(result["liquids"]),
        # "liquidClasses": parse_liquid_classes([result["liquidClasses"]]),
        "labwareOffsets": parse_labware_offsets(result["labwareOffsets"]),
        # **parse_extra_normal_run_fields(result)
    })


def run_endpoint(runtype: RunType) -> str:
    """Return the base HTTP API endpoint for the given type of run."""
    return f"/{runtype.value}s"


def create_run(
        runtype: RunType, offsets: LabwareOffsets, sender: RequestSender
) -> Run:
    """Create a run on the robot.

    :param runtype: The type of run to create.
    :type runtype: gdnasynth.ot2r.commands.runs.RunType
    :param offsets: The initial labware offsets for the run.
    :type offsets: gdnasynth.ot2r.commands.types.LabwareOffsets
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype gdnasynth.ot2r.commands.runs.Run
    """
    resp = sender(
        endpoint=run_endpoint(runtype),
        method="POST",
        data={"data": {"labwareOffsets": offsets}})
    return parse_run_result(resp.json()["data"], runtype)


# 2. Setup:
#     a. Upload labware definition file ==> upload_definition
def add_labware_definition(
        run: Run,
        definition: Path,
        sender: RequestSender
) -> DefinitionUri:
    """Upload a custom labware definition for use by the given run.

    :param run: The run the definition is uploaded for.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param definition: Path to the JSON labware definition file.
    :type definition: pathlib.Path
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype gdnasynth.ot2r.commands.types.DefinitionUri
    """
    resp = sender(
        endpoint=f"{run_endpoint(run.runType)}/{run.id}/labware_definitions",
        method="POST",
        data={"data": json.loads(definition.read_text(encoding="utf-8"))})
    return DefinitionUri(resp.json()["data"]["definitionUri"])


def _command_payload(command: Command) -> dict:
    """Build the JSON payload for a command, omitting unset optionals."""
    payload = {
        "commandType": str(command.commandType),
        "params": command.params,
    }
    if command.intent is not None:
        payload["intent"] = command.intent
    if command.key is not None:
        payload["key"] = str(command.key)
    return payload


def enqueue_command(
        run: Run, command: Command, sender: RequestSender
) -> dict:
    """Enqueue a command on the run.

    :param run: The run to enqueue the command on.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param command: The command to enqueue.
    :type command: gdnasynth.ot2r.commands.types.Command
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype dict
    """
    resp = sender(
        endpoint=f"{run_endpoint(run.runType)}/{run.id}/commands",
        method="POST",
        data={"data": _command_payload(command)})
    return resp.json()["data"]


#     b. Load labware
#     c. Load pipette(s)
#     d. Load protocol (to define liquids)
# 3. Enqueue command(s)


## Steps involved in a maintenance run
#
# 1. Create/Register a run ==> create_run(offsets: LabwareOffsets)
# 2. Setup:
#     a. Upload labware definition file ==> upload_definition
#     b. Load labware
#     c. Load pipette(s)
#     d. Load protocol (to define liquids)
# 3. Enqueue command(s)
# 4. "Play" run
#     can occur before enqueue but with gotchas --
#     all subsequent 'enqueue's MUST happen before the run completes
#     otherwise, the command will fail


## Common (extra) functionality:
#
# 1. Get current run (maintenance or otherwise)
# 2. Get a run (by ID -- maintenance or otherwise)
# 3. Delete a run
# 4. Get list of commands in the run
# 5. Get details about specific command in run
#


## Enqueue Command(s)
#
# The command params vary by command type
