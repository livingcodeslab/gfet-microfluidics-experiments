"""Commands concerning runs."""
import json
import uuid
import datetime
from pathlib import Path

from gdnasynth.ot2r.http import RequestSender
from gdnasynth.ot2r.commands.types import DefinitionURI, LabwareOffsets

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
        # "labware": parse_labware(result["labware"]),
        # "liquids": parse_liquids(result["liquids"]),
        # "liquidClasses": parse_liquid_classes([result["liquidClasses"]]),
        # "labwareOffsets": parse_labware_offsets(result["labwareOffsets"]),
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
) -> DefinitionURI:
    """Upload a custom labware definition for use by the given run.

    :param run: The run the definition is uploaded for.
    :type run: gdnasynth.ot2r.commands.runs.Run
    :param definition: Path to the JSON labware definition file.
    :type definition: pathlib.Path
    :param sender: A pre-configured request sender for the robot.
    :type sender: gdnasynth.ot2r.http.RequestSender

    :rtype gdnasynth.ot2r.commands.types.DefinitionURI
    """
    resp = sender(
        endpoint=f"{run_endpoint(run.runType)}/{run.id}/labware_definitions",
        method="POST",
        data={"data": json.loads(definition.read_text(encoding="utf-8"))})
    return DefinitionURI(resp.json()["data"]["definitionUri"])


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
