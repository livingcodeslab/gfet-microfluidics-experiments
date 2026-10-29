"""A simple OT-2R + SMU workflow, deliberately without robot state tracking.

The workflow:

1. **Pre-flight** — home the robot, then initialise the SMU.
2. **Set up the run** — upload the custom definition, load the labware
   (custom card, reservoir, tiprack) and the pipette.
3. **Per chip well** — enqueue a reservoir -> chip transfer (picking a tip on
   the first pass, since both chips use the same liquid), a `home` to retract
   the pipette, and a `waitForResume`; `play`; wait for the run to pause; prompt
   the operator to act as the multiplexer; sweep the SMU; write the readings to
   CSV; aspirate the dispensed drop back up and dispose of it in the reservoir's
   trash well; then enqueue the next transfer (or the trash/home steps) and
   `play` to resume.
4. **Finish** — wait for the run to succeed, reset the devices, and print the
   names of the files written.

Run it from the repository root:

    python3 workflow_gfet_smu.py

It is intentionally simple: no liquid/tip bookkeeping, config hard-coded below,
and the "multiplexer" is the operator for now.
"""
import csv
import logging
import random
import string
import time
import uuid
from datetime import date
from pathlib import Path

from isswisafre import take_reading

from gdnasynth.generic import float_range
from gdnasynth.keithley import initialise_smu
from gdnasynth.logging import setup_logging
from gdnasynth.ot2r.commands.runs.runs import (add_labware_definition, aspirate,
                                               create_run, delete_run,
                                               dispense, get_run, home,
                                               load_labware, load_pipette,
                                               pick_up_tip, play,
                                               run_endpoint, trash_tip,
                                               wait_for_resume)
from gdnasynth.ot2r.commands.runs.types import EngineStatus, RunType
from gdnasynth.ot2r.commands.types import opentrons_version
from gdnasynth.ot2r.http import make_request_sender
from gdnasynth.ot2r.types import Labware, Pipette

# --- connections -------------------------------------------------------------
ROBOT_URI = "http://OT2CEP20221010R03:31950"
SMU_VISA_ADDRESS = "ASRL/dev/ttyUSB0::INSTR"  # <- set for your SMU
SMU_LINE_FREQUENCY = 50  # Hz
SMU_NPLC = 1.0

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

TIP_WELL = "A1"
RESERVOIR_WELL = "A1"
TRASH_WELL = "A12"
CHIP_WELLS = (("chip-1", "A1"), ("chip-2", "B1"))

# --- pipetting ---------------------------------------------------------------
VOLUME_UL = 10.0
FLOW_RATE = 7.56
# The tip must reach the liquid to pick it up: aspirate at the bottom of the
# well (the server's default origin is `top`, which only skims the surface).
# Add an `offset` (e.g. {"z": 1.0}) if the tip needs to stay off the bottom.
ASPIRATE_WELL_LOCATION = {"origin": "bottom"}
# Dispensing keeps the server default (`top`) unless we decide otherwise.
DISPENSE_WELL_LOCATION = None

# --- SMU sweep ---------------------------------------------------------------
GATE_SWEEP_VOLTAGE = 1.0  # sweep from -this to +this
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
# `send_request` sets no default timeout, so pass an explicit one for homing: a
# stalled request should not hang forever (homing itself can take ~30 s).
# Note: `/robot/move` is a *calibration* move (it requires `target`, `point` and
# `mount`), not an axis jog, so the axes cannot be parked over HTTP; keeping
# them off their hard stops remains an operator step.
ROBOT_TIMEOUT_SECONDS = (10, 120)

# --- timing ------------------------------------------------------------------
POLL_SECONDS = 2
PAUSE_TIMEOUT_SECONDS = 120
RUN_TIMEOUT_SECONDS = 300


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
    for labware in (CARD, TIPRACK, RESERVOIR):
        load_labware(sender, run, labware)
    load_pipette(sender, run, PIPETTE)
    return run


def transfer(sender, run, target_well, *, pick_tip):
    """Enqueue a reservoir -> chip transfer, then retract the pipette.

    The trailing `home` retracts the tip, so it is not left over the chip while
    the SMU takes its readings.
    """
    if pick_tip:
        pick_up_tip(sender, run, PIPETTE, TIPRACK, TIP_WELL)
    aspirate(sender, run, PIPETTE, RESERVOIR, RESERVOIR_WELL, VOLUME_UL,
             FLOW_RATE, well_location=ASPIRATE_WELL_LOCATION)
    dispense(sender, run, PIPETTE, CARD, target_well, VOLUME_UL, FLOW_RATE,
             well_location=DISPENSE_WELL_LOCATION)
    home(sender, run)


def remove_droplet(sender, run, chip_well):
    """Aspirate the dispensed drop back up and dispose of it in the trash well.

    Queued after the SMU acquisition, before the next transfer.
    """
    aspirate(sender, run, PIPETTE, CARD, chip_well, VOLUME_UL, FLOW_RATE,
             well_location=ASPIRATE_WELL_LOCATION)
    dispense(sender, run, PIPETTE, RESERVOIR, TRASH_WELL, VOLUME_UL,
             FLOW_RATE, well_location=DISPENSE_WELL_LOCATION)


def wait_until_paused(sender, run, timeout=PAUSE_TIMEOUT_SECONDS):
    """Block until the run reaches the `waitForResume` pause."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = get_run(sender, run.runType, run.id)
        if state.status == EngineStatus.PAUSED:
            return
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"run {run.id} did not pause within {timeout}s")


def wait_until_finished(sender, run, timeout=RUN_TIMEOUT_SECONDS):
    """Block until the run reaches a terminal state, and return its state."""
    terminal = {EngineStatus.SUCCEEDED, EngineStatus.FAILED,
                EngineStatus.STOPPED}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = get_run(sender, run.runType, run.id)
        if state.status in terminal:
            return state
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"run {run.id} did not finish within {timeout}s")


def prompt_multiplexer(chip, well):
    """Stand in for the multiplexer: wait for the operator to switch over."""
    input(f"  multiplexer: connect the SMU to {chip} ({well}), "
          "then press Enter: ")


def sweep_readings(smu):
    """Yield one SMU reading per (gate, channel) voltage point."""
    gate_voltages = tuple(float_range(
        -GATE_SWEEP_VOLTAGE, GATE_SWEEP_VOLTAGE, GATE_SWEEP_STEP))
    for gate_voltage in gate_voltages:
        for channel_voltage in CHANNEL_VOLTAGES:
            yield take_reading(smu, gate_voltage, channel_voltage)


def output_path(well):
    """Build `<date>-chip-<well>-<random>.csv` under the output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits,
                                    k=6))
    return OUTPUT_DIR / f"{today}-chip-{well}-{suffix}.csv"


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


def stop_and_delete(sender, run):
    """Best-effort cleanup of the run."""
    try:
        sender(endpoint=f"{run_endpoint(run.runType)}/{run.id}/actions",
               method="POST", data={"data": {"actionType": "stop"}})
    except Exception as exc:  # noqa: BLE001 - cleanup should not mask
        print("    could not stop run:", exc)
    time.sleep(2)
    try:
        delete_run(sender, run)
    except Exception as exc:  # noqa: BLE001
        print("    could not delete run:", exc)


def run_workflow(sender, smu, written):
    """Set up the run, drive the chips, and return the final run state.

    Paths of the CSV files written are appended to `written`.
    """
    run = setup_run(sender)
    try:
        first_chip, first_well = CHIP_WELLS[0]
        print(f"3. Transfer to {first_chip} ({first_well})")
        transfer(sender, run, first_well, pick_tip=True)
        wait_for_resume(sender, run, message=f"SMU: {first_chip} {first_well}")
        print("    starting the run")
        play(sender, run)

        for index, (chip, well) in enumerate(CHIP_WELLS):
            print(f"4.{index + 1} Waiting for the pause at {chip} ({well})")
            wait_until_paused(sender, run)

            prompt_multiplexer(chip, well)
            readings = list(sweep_readings(smu))
            path = output_path(well)
            write_readings(path, readings)
            written.append(path)
            print(f"    saved {len(readings)} readings to {path}")

            print(f"5.{index + 1} Removing the drop from {chip} ({well})")
            remove_droplet(sender, run, well)

            if index + 1 < len(CHIP_WELLS):
                next_chip, next_well = CHIP_WELLS[index + 1]
                print(f"    queueing the transfer to {next_chip} ({next_well})")
                transfer(sender, run, next_well, pick_tip=False)
                wait_for_resume(sender, run,
                                message=f"SMU: {next_chip} {next_well}")
            else:
                print("    trashing the tip and homing")
                trash_tip(sender, run, PIPETTE)
                home(sender, run)
            play(sender, run)

        print("6. Waiting for the run to finish")
        return wait_until_finished(sender, run)
    finally:
        print("7. Cleaning up the run")
        stop_and_delete(sender, run)


def main():
    """Pre-flight the devices, run the workflow, then reset everything."""
    setup_logging("info", logging.getLogger())
    sender = make_request_sender(ROBOT_URI, opentrons_version("*"))
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

        print("8. Reset: robot")
        home_robot(sender)
        print("9. Reset: SMU")
        reset_smu(smu)

        print("workflow complete")
    finally:
        if written:
            print("files written:")
            for path in written:
                print("   ", path)


if __name__ == "__main__":
    main()
