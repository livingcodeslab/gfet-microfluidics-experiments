"""A 3-reagent OT-2R + SMU workflow: dilute, dispense, measure, wash.

The workflow:

1. **Pre-flight** — home the robot, then initialise the SMU (60 Hz mains,
   NPLC 6.75025).
2. **Set up the run** — upload the custom definition, load the card, tiprack,
   water reservoir and the 96-well dilution plate, and the p20 pipette.
3. **Prepare the reagents** — dilute 1X PBS down to 0.1X, 0.01X, 0.001X and
   0.0005X in the dilution plate (18 uL units, 1:10 steps plus one 1:2 step).
4. **Acquire** — for each chip and then each reagent (ascending
   concentration): transfer 10 uL onto the chip, retract the pipette, pause the
   run, prompt the operator to switch the multiplexer, sweep the SMU, save the
   readings, remove the droplet, and wash the chip with water.
5. **Finish** — home the robot, wait for the run to succeed, reset the devices
   and print the names of the files written.

Names of the files written follow
``<date>-chip-<chip>-<reagent>-<random>.csv``, where ``<random>`` is generated
once per invocation and shared by every file.

Run it from the repository root:

    python3 workflow_gfet_smu_dilutions.py

It is intentionally simple: no liquid/tip bookkeeping, config hard-coded below,
and the "multiplexer" is the operator for now. The wash sequence is open-coded
here until we extract it as a complex operation (see the run-control design
notes, section 5.10).
"""
import csv
import logging
import random
import string
import time
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator

from isswisafre import take_reading

from gdnasynth.generic import float_range
from gdnasynth.keithley import initialise_smu
from gdnasynth.logging import setup_logging
from gdnasynth.ot2r.commands.runs.runs import (add_labware_definition, aspirate,
                                               create_run, delete_run,
                                               dispense, get_run, home,
                                               load_labware, load_pipette,
                                               pick_up_tip, play,
                                               retract_pipettes, run_endpoint,
                                               trash_tip, wait_for_resume)
from gdnasynth.ot2r.commands.runs.types import EngineStatus, RunType
from gdnasynth.ot2r.commands.types import opentrons_version
from gdnasynth.ot2r.http import make_request_sender
from gdnasynth.ot2r.types import Labware, Pipette

# --- connections -------------------------------------------------------------
ROBOT_URI = "http://OT2CEP20221010R03:31950"
# Bound the wait for every request: without a timeout a stalled connection
# blocks the script forever (a polling loop cannot notice anything then).
REQUEST_TIMEOUT_SECONDS = (10, 60)
SMU_VISA_ADDRESS = "ASRL/dev/ttyUSB0::INSTR"  # <- set for your SMU
SMU_LINE_FREQUENCY = 60  # Hz
SMU_NPLC = 6.75025

# --- deck --------------------------------------------------------------------
DEFINITION = Path("OT2_labware_definition_graphenea_card.json")
PIPETTE = Pipette(
    pipette_name="p20_single_gen2", mount="left",
    pipette_id=uuid.UUID("7806a233-8012-4d99-8887-970935f103e1"))
CARD = Labware(
    labware_name="livingcodeslab_graphenea_card_adapter", load_slot=1,
    namespace="livingcodeslab",
    labware_id=uuid.UUID("c9c762e1-8205-4ccd-be32-6535fd0e9514"))
TIPRACK = Labware(
    labware_name="opentrons_96_filtertiprack_20ul", load_slot=7,
    labware_id=uuid.UUID("32dbb5b7-710d-428b-bff0-03e31351e25f"))
RESERVOIR = Labware(
    labware_name="nest_12_reservoir_15ml", load_slot=3,
    labware_id=uuid.UUID("fe305793-e2b6-40ce-94d7-2b55549b1b57"))
DILUTION_PLATE = Labware(
    labware_name="corning_96_wellplate_330ul", load_slot=5,
    labware_id=uuid.UUID("5f0f4b8c-2a5f-4c3e-9a2c-1d6f3a9c8b21"))

WATER_WELL = "A1"    # in the reservoir
TRASH_WELL = "A12"   # in the reservoir
CHIP_WELLS = (("1", "A1"), ("2", "B1"))

# --- pipetting ---------------------------------------------------------------
FLOW_RATE = 7.56

# The tip must reach the liquid: aspirate at the bottom of the well.
ASPIRATE_WELL_LOCATION = {"origin": "bottom"}
# Dilutions: dispense into the liquid, at the bottom of the well.
DILUTION_DISPENSE_WELL_LOCATION = {"origin": "bottom"}
# Chips: dispense at the bottom too — with the corrected well `z` this puts the
# tip exactly on the chip surface without pressing it into its socket.
CHIP_DISPENSE_WELL_LOCATION = {"origin": "bottom"}

# --- dilutions ---------------------------------------------------------------
# 18 uL units keep every dispense inside the p20's 1-20 uL range.
DILUTION_UNIT_UL = 18.0
DILUTION_UNIT_COUNT = 9   # 9 x 18 = 162 uL of water per 1:10 well
HALF_DILUTION_UNIT_COUNT = 5  # 5 x 18 = 90 uL of water for the 1:2 well
MIX_VOLUME_UL = 18.0
MIX_CYCLES = 3

# Dilution wells in the plate: A1 holds the 1X PBS, A2..A5 the dilutions.
PURE_1X_WELL = "A1"
# (target well, source well, number of 18 uL transfers into the target)
DILUTION_STEPS = (
    ("A2", "A1", 1),   # 0.1X
    ("A3", "A2", 1),   # 0.01X
    ("A4", "A3", 1),   # 0.001X
    ("A5", "A4", HALF_DILUTION_UNIT_COUNT),  # 0.0005X (1:2)
)
# (target well, number of 18 uL water dispenses into the target)
WATER_FOR_DILUTIONS = (
    ("A2", DILUTION_UNIT_COUNT),
    ("A3", DILUTION_UNIT_COUNT),
    ("A4", DILUTION_UNIT_COUNT),
    ("A5", HALF_DILUTION_UNIT_COUNT),
)


@dataclass(frozen=True)
class Reagent:
    """A liquid to put on the chip, with its file-name tag and source."""
    tag: str
    labware: Labware
    well: str


# Ascending concentration: water (0X), 0.0005X, 0.001X.
REAGENTS = (
    Reagent("water", RESERVOIR, WATER_WELL),
    Reagent("0p0005PBS", DILUTION_PLATE, "A5"),
    Reagent("00p1PBS", DILUTION_PLATE, "A4"),
)

# --- acquisition -------------------------------------------------------------
TRANSFER_VOLUME_UL = 10.0
# Surface tension leaves a film behind on the chip, so aspirate more than we
# dispensed when removing the droplet (picking up a little air) and discard it.
DROPLET_ASPIRATE_VOLUME_UL = 1.5 * TRANSFER_VOLUME_UL
WASH_VOLUME_UL = 10.0
WASH_CYCLES = 5
WASH_MIX_CYCLES = 3

# --- SMU sweep ---------------------------------------------------------------
GATE_SWEEP_VOLTAGE = 1.5  # sweep from -this to +this
GATE_SWEEP_STEP = 0.1
CHANNEL_VOLTAGES = (0.05, -0.05)
READING_FIELDS = (
    "timestamp",
    "provided_gate_voltage",
    "provided_channel_voltage",
    "drain_voltage",
    "drain_current",
    "measured_gate_voltage",
    "measured_gate_current")

# --- output ------------------------------------------------------------------
OUTPUT_DIR = Path("sweeps")

# --- robot homing ------------------------------------------------------------
# `send_request` sets no default timeout, so pass an explicit one for homing.
ROBOT_TIMEOUT_SECONDS = (10, 120)

# --- timing ------------------------------------------------------------------
POLL_SECONDS = 2
# No wall-clock timeout: segments legitimately take minutes (the dilution block
# is ~120 commands, a wash ~45). Instead we fail only if no command completes
# for this long.
STALL_TIMEOUT_SECONDS = 300


def home_robot(sender):
    """Home the robot, allowing longer than the transport's default timeout."""
    sender(endpoint="/robot/home", method="POST",
           data={"target": "robot"}, timeout=ROBOT_TIMEOUT_SECONDS)


def preflight_smu():
    """Initialise the SMU (this also stabilises it)."""
    return initialise_smu(SMU_VISA_ADDRESS, SMU_LINE_FREQUENCY, SMU_NPLC)


def setup_run(sender):
    """Create a normal run and load the custom definition, labware, pipette."""
    run = create_run(sender, RunType.NORMALRUN, ())
    print("    run:", run.id)

    add_labware_definition(sender, run, DEFINITION)
    for labware in (CARD, TIPRACK, RESERVOIR, DILUTION_PLATE):
        load_labware(sender, run, labware)
    load_pipette(sender, run, PIPETTE)
    return run


def tip_wells() -> Iterator[str]:
    """Yield tiprack wells in row-major order (A1, A2, ..., H12)."""
    for row in "ABCDEFGH":
        for column in range(1, 13):
            yield f"{row}{column}"


def mix(sender, run, labware, well, volume, cycles, *, dispense_location):
    """Enqueue `cycles` aspirate/dispense pairs in one well."""
    for _ in range(cycles):
        aspirate(sender, run, PIPETTE, labware, well, volume, FLOW_RATE,
                 well_location=ASPIRATE_WELL_LOCATION)
        dispense(sender, run, PIPETTE, labware, well, volume, FLOW_RATE,
                 well_location=dispense_location)


def prepare_reagents(sender, run, tips):
    """Dilute 1X PBS into 0.1X, 0.01X, 0.001X and 0.0005X in the plate."""
    print("3. Diluting 1X PBS")

    # Water first: one tip re-used for the same source.
    pick_up_tip(sender, run, PIPETTE, TIPRACK, next(tips))
    for well, dispenses in WATER_FOR_DILUTIONS:
        for _ in range(dispenses):
            aspirate(sender, run, PIPETTE, RESERVOIR, WATER_WELL,
                     DILUTION_UNIT_UL, FLOW_RATE,
                     well_location=ASPIRATE_WELL_LOCATION)
            dispense(sender, run, PIPETTE, DILUTION_PLATE, well,
                     DILUTION_UNIT_UL, FLOW_RATE,
                     well_location=DILUTION_DISPENSE_WELL_LOCATION)
    trash_tip(sender, run, PIPETTE)

    # Then the serial transfers, each with a fresh tip.
    for target, source, transfers in DILUTION_STEPS:
        print(f"    {source} -> {target} ({transfers} x {DILUTION_UNIT_UL} uL)")
        pick_up_tip(sender, run, PIPETTE, TIPRACK, next(tips))
        for _ in range(transfers):
            aspirate(sender, run, PIPETTE, DILUTION_PLATE, source,
                     DILUTION_UNIT_UL, FLOW_RATE,
                     well_location=ASPIRATE_WELL_LOCATION)
            dispense(sender, run, PIPETTE, DILUTION_PLATE, target,
                     DILUTION_UNIT_UL, FLOW_RATE,
                     well_location=DILUTION_DISPENSE_WELL_LOCATION)
        mix(sender, run, DILUTION_PLATE, target, MIX_VOLUME_UL, MIX_CYCLES,
            dispense_location=DILUTION_DISPENSE_WELL_LOCATION)
        trash_tip(sender, run, PIPETTE)


def transfer_to_chip(sender, run, chip_well, reagent, tips):
    """Put one aliquot of a reagent on the chip and retract the pipette."""
    pick_up_tip(sender, run, PIPETTE, TIPRACK, next(tips))
    aspirate(sender, run, PIPETTE, reagent.labware, reagent.well,
             TRANSFER_VOLUME_UL, FLOW_RATE,
             well_location=ASPIRATE_WELL_LOCATION)
    dispense(sender, run, PIPETTE, CARD, chip_well, TRANSFER_VOLUME_UL,
             FLOW_RATE, well_location=CHIP_DISPENSE_WELL_LOCATION)
    retract_pipettes(sender, run, [PIPETTE])


def remove_droplet(sender, run, chip_well):
    """Aspirate the drop off the chip (plus some extra) and trash it.

    More is aspirated than was dispensed: surface tension leaves a film behind,
    so we deliberately over-aspirate and discard the surplus.
    """
    aspirate(sender, run, PIPETTE, CARD, chip_well, DROPLET_ASPIRATE_VOLUME_UL,
             FLOW_RATE, well_location=ASPIRATE_WELL_LOCATION)
    dispense(sender, run, PIPETTE, RESERVOIR, TRASH_WELL,
             DROPLET_ASPIRATE_VOLUME_UL, FLOW_RATE,
             well_location=DILUTION_DISPENSE_WELL_LOCATION)


def wash_chip(sender, run, chip_well, tips):
    """Wash the chip with water, then leave it (nearly) dry.

    Each of the `WASH_CYCLES` cycles dispenses `WASH_VOLUME_UL` of water on the
    chip, mixes it `WASH_MIX_CYCLES` times, and removes it to the trash. The
    residue left behind is a thin film diluted towards pure water.
    """
    pick_up_tip(sender, run, PIPETTE, TIPRACK, next(tips))
    for _ in range(WASH_CYCLES):
        aspirate(sender, run, PIPETTE, RESERVOIR, WATER_WELL, WASH_VOLUME_UL,
                 FLOW_RATE, well_location=ASPIRATE_WELL_LOCATION)
        dispense(sender, run, PIPETTE, CARD, chip_well, WASH_VOLUME_UL,
                 FLOW_RATE, well_location=CHIP_DISPENSE_WELL_LOCATION)
        mix(sender, run, CARD, chip_well, WASH_VOLUME_UL, WASH_MIX_CYCLES,
            dispense_location=CHIP_DISPENSE_WELL_LOCATION)
        aspirate(sender, run, PIPETTE, CARD, chip_well, WASH_VOLUME_UL,
                 FLOW_RATE, well_location=ASPIRATE_WELL_LOCATION)
        dispense(sender, run, PIPETTE, RESERVOIR, TRASH_WELL, WASH_VOLUME_UL,
                 FLOW_RATE, well_location=DILUTION_DISPENSE_WELL_LOCATION)
    trash_tip(sender, run, PIPETTE)


_TERMINAL_STATES = {EngineStatus.SUCCEEDED, EngineStatus.FAILED,
                    EngineStatus.STOPPED}
_BAD_RUN_STATES = {
    EngineStatus.FAILED,
    EngineStatus.STOPPED,
    EngineStatus.STOP_REQUESTED,
    EngineStatus.AWAITING_RECOVERY,
    EngineStatus.AWAITING_RECOVERY_PAUSED,
    EngineStatus.AWAITING_RECOVERY_BLOCKED_BY_OPEN_DOOR,
}


def command_page(sender, run, cursor):
    """Fetch one command (and the total count) from the run's command list."""
    body = sender(
        endpoint=f"{run_endpoint(run.runType)}/{run.id}/commands",
        method="GET",
        data={"cursor": cursor, "pageLength": 1},
    ).json()
    page = body["data"]
    meta = body.get("meta") or {}
    return (page[0] if page else None), meta.get("totalLength", 0)


def scan_commands(sender, run, start=0):
    """Walk forward from `start` to the first command that has not succeeded.

    Commands run in order, so the succeeded ones are always a prefix: walking
    from the last known index costs about one request per completed command.

    :returns: ``(index, total, command)``; `command` is ``None`` when all have
        succeeded.
    """
    index = start
    command, total = command_page(sender, run, index)
    while (index < total and command is not None
           and command.get("status") == "succeeded"):
        index += 1
        command, total = command_page(sender, run, index)
    if index >= total:
        # A `cursor` past the end of the list clamps to the last command, so
        # stop explicitly instead of walking past it forever: without this the
        # loop never returns once every command has succeeded.
        return total, total, None
    return index, total, command


def describe_progress(index, total, command):
    """Describe the current command, for an error message."""
    if command is None:
        return f"{index}/{total} commands succeeded"
    error = command.get("error") or {}
    detail = error.get("detail")
    return (f"{index}/{total} commands succeeded; next is "
            f"{command['commandType']} ({command['status']})"
            + (f": {detail}" if detail else ""))


def wait_for_run(sender, run, *, pause, what, progress,
                 stall_timeout=STALL_TIMEOUT_SECONDS):
    """Poll the run until it pauses (or finishes), failing fast on errors.

    There is deliberately no wall-clock timeout: a segment may legitimately take
    minutes. We fail when a command fails, when the run stops or needs
    recovery, or when no command has completed for `stall_timeout` seconds.

    `progress` is a one-key dict (``{"index": 0}``) remembering how far the
    succeeded commands reach between calls.
    """
    index = progress.get("index", 0)
    last_index = -1
    last_progress = time.monotonic()
    while True:
        index, total, command = scan_commands(sender, run, index)
        progress["index"] = index
        state = get_run(sender, run.runType, run.id)
        if pause and state.status == EngineStatus.PAUSED:
            return state
        if not pause and state.status in _TERMINAL_STATES:
            return state
        if command is not None and command.get("status") == "failed":
            raise RuntimeError(
                f"run {run.id} failed while waiting for {what}: "
                f"{describe_progress(index, total, command)}")
        if state.status in _BAD_RUN_STATES:
            raise RuntimeError(
                f"run {run.id} did not reach {what}: {state.status.value}; "
                f"{describe_progress(index, total, command)}")
        if index != last_index:
            last_index = index
            last_progress = time.monotonic()
        elif time.monotonic() - last_progress > stall_timeout:
            raise TimeoutError(
                f"run {run.id} made no progress for {stall_timeout}s while "
                f"waiting for {what}: "
                f"{describe_progress(index, total, command)}")
        time.sleep(POLL_SECONDS)


def wait_until_paused(sender, run, *, what="the pause", progress):
    """Block until the run reaches the `waitForResume` pause."""
    return wait_for_run(sender, run, pause=True, what=what, progress=progress)


def wait_until_finished(sender, run, *, what="the end", progress):
    """Block until the run reaches a terminal state, and return its state."""
    return wait_for_run(sender, run, pause=False, what=what, progress=progress)


def prompt_multiplexer(chip):
    """Stand in for the multiplexer: wait for the operator to switch over."""
    input(f"  multiplexer: connect the SMU to chip {chip}, then press Enter: ")


def sweep_readings(smu):
    """Yield one SMU reading per (gate, channel) voltage point."""
    gate_voltages = tuple(float_range(
        -GATE_SWEEP_VOLTAGE, GATE_SWEEP_VOLTAGE, GATE_SWEEP_STEP))
    for gate_voltage in gate_voltages:
        for channel_voltage in CHANNEL_VOLTAGES:
            yield take_reading(smu, gate_voltage, channel_voltage)


def random_string(length=6) -> str:
    """Generate the random string shared by every file of this invocation."""
    return "".join(random.choices(string.ascii_lowercase + string.digits,
                                  k=length))


def output_path(chip, reagent, randstr):
    """Build `<date>-chip-<chip>-<reagent>-<random>.csv`."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    return OUTPUT_DIR / f"{today}-chip-{chip}-{reagent}-{randstr}.csv"


def write_readings(path, readings):
    """Write the readings to a CSV file."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=READING_FIELDS)
        writer.writeheader()
        writer.writerows(readings)


def reset_smu(smu):
    """Turn the SMU outputs off."""
    smu.smua.source.output = smu.smua.OUTPUT_OFF
    smu.smub.source.output = smu.smub.OUTPUT_OFF


def stop_and_delete(sender, run, attempts=5):
    """Best-effort cleanup: stop the run, wait for it to settle, then delete.

    A run cannot be deleted while it is still active, so the delete is retried
    for a few seconds after the stop (the run goes through `stop-requested`).
    """
    try:
        sender(endpoint=f"{run_endpoint(run.runType)}/{run.id}/actions",
               method="POST", data={"data": {"actionType": "stop"}})
    except Exception as exc:  # noqa: BLE001 - cleanup should not mask
        print("    could not stop run:", exc)
    last_error = None
    for _ in range(attempts):
        time.sleep(2)
        try:
            delete_run(sender, run)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    print("    could not delete run:", last_error)


def acquire(sender, run, smu, chip, chip_well, reagent, randstr, written):
    """Sweep the SMU, save the readings and return the file path."""
    readings = list(sweep_readings(smu))
    path = output_path(chip, reagent.tag, randstr)
    write_readings(path, readings)
    written.append(path)
    print(f"    saved {len(readings)} readings to {path}")


def run_workflow(sender, smu, written):
    """Run the dilutions and the acquisition loop; return the final state."""
    run = setup_run(sender)
    tips = tip_wells()
    progress = {"index": 0}
    try:
        prepare_reagents(sender, run, tips)

        # Barrier: pause once the dilutions are done, so the script can report
        # progress (and the operator can check the plate) before acquiring.
        wait_for_resume(sender, run, message="dilutions complete")
        print("4. Running the dilutions")
        play(sender, run)
        wait_until_paused(sender, run, what="the dilution barrier",
                          progress=progress)
        print("    dilutions complete")

        randstr = random_string()
        print("5. Generating file suffix:", randstr)

        first_chip, first_well = CHIP_WELLS[0]
        print(f"6. Transfer to {first_chip} ({first_well}) / {REAGENTS[0].tag}")
        transfer_to_chip(sender, run, first_well, REAGENTS[0], tips)
        wait_for_resume(sender, run,
                        message=f"SMU: {first_chip} {REAGENTS[0].tag}")
        print("    starting the run")
        play(sender, run)

        for chip_index, (chip, chip_well) in enumerate(CHIP_WELLS):
            for reagent_index, reagent in enumerate(REAGENTS):
                print(f"7. Waiting for the pause at {chip} / {reagent.tag}")
                wait_until_paused(
                    sender, run,
                    what=f"the pause at chip {chip} / {reagent.tag}",
                    progress=progress)

                if reagent_index == 0:
                    prompt_multiplexer(chip)
                acquire(sender, run, smu, chip, chip_well, reagent, randstr,
                        written)

                print("    removing the drop")
                remove_droplet(sender, run, chip_well)
                trash_tip(sender, run, PIPETTE)

                print("    washing the chip")
                wash_chip(sender, run, chip_well, tips)

                is_last = (chip_index == len(CHIP_WELLS) - 1
                           and reagent_index == len(REAGENTS) - 1)
                if is_last:
                    print("    homing the robot")
                    home(sender, run)
                else:
                    next_chip, next_well, next_reagent = _next_target(
                        chip_index, reagent_index)
                    print(f"    queueing {next_chip} / {next_reagent.tag}")
                    transfer_to_chip(sender, run, next_well, next_reagent,
                                     tips)
                    wait_for_resume(
                        sender, run, message=f"SMU: {next_chip} "
                                             f"{next_reagent.tag}")
                play(sender, run)

        print("8. Waiting for the run to finish")
        return wait_until_finished(sender, run, progress=progress)
    finally:
        print("9. Cleaning up the run")
        stop_and_delete(sender, run)


def _next_target(chip_index, reagent_index):
    """Return the (chip, well, reagent) following the given position."""
    if reagent_index + 1 < len(REAGENTS):
        chip, well = CHIP_WELLS[chip_index]
        return chip, well, REAGENTS[reagent_index + 1]
    chip, well = CHIP_WELLS[chip_index + 1]
    return chip, well, REAGENTS[0]


def main():
    """Pre-flight the devices, run the workflow, then reset everything."""
    setup_logging("info", logging.getLogger())
    sender = make_request_sender(ROBOT_URI, opentrons_version("*"),
                                 timeout=REQUEST_TIMEOUT_SECONDS)
    written = []

    try:
        print("1. Pre-flight: robot")
        home_robot(sender)
        print("2. Pre-flight: SMU")
        smu = preflight_smu()

        final = run_workflow(sender, smu, written)
        print("    final status:", final.status)
        if final.status != EngineStatus.SUCCEEDED:
            raise RuntimeError(f"run finished with status {final.status}")

        print("Reset: robot")
        home_robot(sender)
        print("Reset: SMU")
        reset_smu(smu)

        print("workflow complete")
    finally:
        if written:
            print("files written:")
            for path in written:
                print("   ", path)


if __name__ == "__main__":
    main()
