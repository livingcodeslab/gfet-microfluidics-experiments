"""Commands concerning runs."""
import json
import uuid
import logging
import datetime
from pathlib import Path
from typing import Optional, Sequence, Union

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

from gdnasynth.ot2r.types import LabwareConfig, PipetteConfig

from .types import Run, RunType, EngineStatus

logger = logging.getLogger(__name__)

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
        sender: RequestSender,
        runtype: RunType,
        offsets: LabwareOffsets,
        protocol_id: Optional[uuid.UUID] = None
) -> Run:
    """Create a run on the robot.

    :param runtype: The type of run to create.
    :type runtype: gdnasynth.ot2r.commands.runs.RunType
    :param offsets: The initial labware offsets for the run.
    :type offsets: gdnasynth.ot2r.commands.types.LabwareOffsets
    :param protocol_id: An optional protocol to associate with the run
        (normal runs only).
    :type protocol_id: uuid.UUID, optional
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype gdnasynth.ot2r.commands.runs.Run
    """
    data: dict = {"labwareOffsets": offsets}
    if protocol_id is not None:
        data["protocolId"] = str(protocol_id)
    resp = sender(
        endpoint=run_endpoint(runtype),
        method="POST",
        data={"data": data})
    logger.debug("Response text (create_run): %s", resp.text)
    return parse_run_result(resp.json()["data"], runtype)


# 2. Setup:
#     a. Upload labware definition file ==> upload_definition
def add_labware_definition(
        sender: RequestSender,
        run: Run,
        definition: Path
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


def load_labware(
        sender: RequestSender, run: Run, labware: LabwareConfig
) -> dict:
    """Enqueue a ``loadLabware`` command for the run.

    :param run: The run to load the labware into.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param labware: The labware configuration to load.
    :type labware: gdnasynth.ot2r.types.LabwareConfig
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype dict
    """
    command = Command(
        commandType=NonEmptyString("loadLabware"),
        params={
            "location": {"slotName": str(labware.load_slot)},
            "loadName": labware.labware_name,
            "namespace": labware.namespace,
            "version": labware.version,
            "labwareId": str(labware.labware_id),
        },
        intent="setup")
    return enqueue_command(sender, run, command)


def load_pipette(
        sender: RequestSender, run: Run, pipette: PipetteConfig
) -> dict:
    """Enqueue a ``loadPipette`` command for the run.

    :param run: The run to load the pipette into.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param pipette: The pipette configuration to load.
    :type pipette: gdnasynth.ot2r.types.PipetteConfig
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype dict
    """
    command = Command(
        commandType=NonEmptyString("loadPipette"),
        params={
            "pipetteName": pipette.pipette_name,
            "mount": pipette.mount,
            "pipetteId": str(pipette.pipette_id),
        },
        intent="setup")
    return enqueue_command(sender, run, command)


def enqueue_command(
        sender: RequestSender, run: Run, command: Command
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
        data={"data": command})
    logger.debug("Response text (enqueue_command): %s", resp.text)
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


def pick_up_tip(
        sender: RequestSender,
        run: Run,
        pipette: PipetteConfig,
        labware: LabwareConfig,
        well_name: str,
        well_location: Optional[dict] = None
) -> dict:
    """Enqueue a ``pickUpTip`` command for the run.

    :param run: The run to pick up a tip in.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param pipette: The pipette to use.
    :type pipette: gdnasynth.ot2r.types.PipetteConfig
    :param labware: The tiprack to pick the tip from.
    :type labware: gdnasynth.ot2r.types.LabwareConfig
    :param well_name: The well to pick the tip from.
    :type well_name: str
    :param well_location: An optional well location, e.g.
        ``{"origin": "bottom"}``.
    :type well_location: dict, optional
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype dict
    """
    params: dict = {
        "pipetteId": str(pipette.pipette_id),
        "labwareId": str(labware.labware_id),
        "wellName": well_name,
    }
    if well_location is not None:
        params["wellLocation"] = well_location
    command = Command(
        commandType=NonEmptyString("pickUpTip"),
        params=params,
        intent="protocol")
    return enqueue_command(sender, run, command)


def aspirate(
        sender: RequestSender,
        run: Run,
        pipette: PipetteConfig,
        labware: LabwareConfig,
        well_name: str,
        volume: float,
        flow_rate: float,
        well_location: Optional[dict] = None
) -> dict:
    """Enqueue an ``aspirate`` command for the run.

    :param run: The run to aspirate in.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param pipette: The pipette to use.
    :type pipette: gdnasynth.ot2r.types.PipetteConfig
    :param labware: The labware to aspirate from.
    :type labware: gdnasynth.ot2r.types.LabwareConfig
    :param well_name: The well to aspirate from.
    :type well_name: str
    :param volume: The volume to aspirate, in µL.
    :type volume: float
    :param flow_rate: The flow rate to aspirate at, in µL/s.
    :type flow_rate: float
    :param well_location: An optional well location, e.g.
        ``{"origin": "center"}``.
    :type well_location: dict, optional
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype dict
    """
    params = {
        "pipetteId": str(pipette.pipette_id),
        "labwareId": str(labware.labware_id),
        "wellName": well_name,
        "volume": volume,
        "flowRate": flow_rate,
    }
    if well_location is not None:
        params["wellLocation"] = well_location
    command = Command(
        commandType=NonEmptyString("aspirate"),
        params=params,
        intent="protocol")
    return enqueue_command(sender, run, command)


def dispense(
        sender: RequestSender,
        run: Run,
        pipette: PipetteConfig,
        labware: LabwareConfig,
        well_name: str,
        volume: float,
        flow_rate: float,
        well_location: Optional[dict] = None
) -> dict:
    """Enqueue a ``dispense`` command for the run.

    :param run: The run to dispense in.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param pipette: The pipette to use.
    :type pipette: gdnasynth.ot2r.types.PipetteConfig
    :param labware: The labware to dispense to.
    :type labware: gdnasynth.ot2r.types.LabwareConfig
    :param well_name: The well to dispense to.
    :type well_name: str
    :param volume: The volume to dispense, in µL.
    :type volume: float
    :param flow_rate: The flow rate to dispense at, in µL/s.
    :type flow_rate: float
    :param well_location: An optional well location, e.g.
        ``{"origin": "center"}``.
    :type well_location: dict, optional
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype dict
    """
    params = {
        "pipetteId": str(pipette.pipette_id),
        "labwareId": str(labware.labware_id),
        "wellName": well_name,
        "volume": volume,
        "flowRate": flow_rate,
    }
    if well_location is not None:
        params["wellLocation"] = well_location
    command = Command(
        commandType=NonEmptyString("dispense"),
        params=params,
        intent="protocol")
    return enqueue_command(sender, run, command)


def drop_tip(
        sender: RequestSender,
        run: Run,
        pipette: PipetteConfig,
        labware: LabwareConfig,
        well_name: str,
        well_location: Optional[dict] = None
) -> dict:
    """Enqueue a ``dropTip`` command for the run.

    :param run: The run to drop the tip in.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param pipette: The pipette to use.
    :type pipette: gdnasynth.ot2r.types.PipetteConfig
    :param labware: The labware to drop the tip into.
    :type labware: gdnasynth.ot2r.types.LabwareConfig
    :param well_name: The well to drop the tip into.
    :type well_name: str
    :param well_location: An optional well location, e.g.
        ``{"origin": "top"}``.
    :type well_location: dict, optional
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype dict
    """
    params: dict = {
        "pipetteId": str(pipette.pipette_id),
        "labwareId": str(labware.labware_id),
        "wellName": well_name,
    }
    if well_location is not None:
        params["wellLocation"] = well_location
    command = Command(
        commandType=NonEmptyString("dropTip"),
        params=params,
        intent="protocol")
    return enqueue_command(sender, run, command)


def home(sender: RequestSender, run: Run) -> dict:
    """Enqueue a ``home`` command for the run.

    :param run: The run to home.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype dict
    """
    command = Command(
        commandType=NonEmptyString("home"),
        params={},
        intent="protocol")
    return enqueue_command(sender, run, command)


def trash_tip(
        sender: RequestSender, run: Run, pipette: PipetteConfig
) -> tuple[dict, dict]:
    """Dispose of the pipette's tip in the OT-2's fixed trash.

    Enqueues ``moveToAddressableAreaForDropTip`` followed by
    ``dropTipInPlace``.  OT-2 only: robots with a movable trash area would
    need a different implementation.

    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender
    :param run: The run to dispose of the tip in.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param pipette: The pipette whose tip to dispose of.
    :type pipette: gdnasynth.ot2r.types.PipetteConfig

    :rtype tuple[dict, dict]
    """
    move = Command(
        commandType=NonEmptyString("moveToAddressableAreaForDropTip"),
        params={
            "pipetteId": str(pipette.pipette_id),
            "addressableAreaName": "fixedTrash",
        },
        intent="protocol")
    drop = Command(
        commandType=NonEmptyString("dropTipInPlace"),
        params={"pipetteId": str(pipette.pipette_id)},
        intent="protocol")
    return (
        enqueue_command(sender, run, move),
        enqueue_command(sender, run, drop),
    )


def get_run(
        sender: RequestSender, runtype: RunType, run_id: uuid.UUID
) -> Run:
    """Get a run by its id.

    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender
    :param runtype: The type of run to get.
    :type runtype: gdnasynth.ot2r.commands.runs.RunType
    :param run_id: The id of the run to get.
    :type run_id: uuid.UUID

    :rtype gdnasynth.ot2r.commands.runs.Run
    """
    resp = sender(
        endpoint=f"{run_endpoint(runtype)}/{run_id}",
        method="GET",
        data={})
    return parse_run_result(resp.json()["data"], runtype)


def get_current_run(sender: RequestSender, runtype: RunType) -> Run:
    """Get the current run.

    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender
    :param runtype: The type of run to get.
    :type runtype: gdnasynth.ot2r.commands.runs.RunType

    :rtype gdnasynth.ot2r.commands.runs.Run
    """
    resp = sender(
        endpoint=f"{run_endpoint(runtype)}/current_run",
        method="GET",
        data={})
    return parse_run_result(resp.json()["data"], runtype)


def delete_run(sender: RequestSender, run: Run) -> None:
    """Delete a run.

    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender
    :param run: The run to delete.
    :type run: gdnasynth.ot2r.commands.runs.Run

    :rtype None
    """
    sender(
        endpoint=f"{run_endpoint(run.runType)}/{run.id}",
        method="DELETE",
        data={})


def list_commands(sender: RequestSender, run: Run) -> Sequence[dict]:
    """List the run's commands.

    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender
    :param run: The run whose commands to list.
    :type run: gdnasynth.ot2r.commands.runs.Run

    :rtype Sequence[dict]
    """
    resp = sender(
        endpoint=f"{run_endpoint(run.runType)}/{run.id}/commands",
        method="GET",
        data={})
    return resp.json()["data"]


def get_command(
        sender: RequestSender, run: Run, command_id: uuid.UUID
) -> dict:
    """Get a single command from the run by its id.

    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender
    :param run: The run the command belongs to.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param command_id: The id of the command to get.
    :type command_id: uuid.UUID

    :rtype dict
    """
    resp = sender(
        endpoint=(f"{run_endpoint(run.runType)}/{run.id}/commands/"
                  f"{command_id}"),
        method="GET",
        data={})
    return resp.json()["data"]
