import sys
import csv
import copy
import time
import logging
import threading
from pathlib import Path
from typing import Optional
from argparse import Namespace, ArgumentParser

import serial.tools.list_ports
from keithley2600 import Keithley2600

from gfet.keithley import connect, select_visa_address

from logging_utils import set_loggers_level
from microfluidics import (collect,
                           Channel,
                           wash_chip,
                           wash_common,
                           vent_common,
                           vent_chip2waste,
                           REAGENT_CHANNELS,
                           prime_wash_to_channel,
                           prime_reagent_to_channel)

logger = logging.getLogger(__name__)
logging.basicConfig(
    encoding="utf-8",
    format="%(asctime)s - %(name)s - %(levelname)s — %(message)s")


def select_microfluidics_device_port(**kwargs) -> serial.Serial:
    """Enable selection of serial port.

    Take all the arguments to serial.Serial except `port` as keyword arguments
    and passes them on."""
    _kwargs = copy.deepcopy(kwargs)
    remove_empty = _kwargs.pop("remove_empty", True)
    print("Port#\tDevice")
    ports = serial.tools.list_ports.comports()
    if remove_empty:
        ports = [port for port in ports
                 if any((port.product, port.manufacturer, port.vid, port.pid))]
    for idx, port in enumerate(ports, start=1):
        print(
            f"{idx:4}:\t{port.device} => {port.manufacturer}:"
            f"{port.product} ({port.vid}:{port.pid})")

    try:
        selection = int(input(
            "Choose your microfluidics device "
            f"('Port#': {1} to {len(ports)}): "))
        assert( 0 < selection <= len(ports)), "Invalid selection."
        return serial.Serial(
            ports[selection - 1].device,
            **_kwargs)
    except (ValueError, AssertionError) as _exc:
        print("You made an invalid selection. Exiting!", file=sys.stderr)
        print(_exc)
    sys.exit(1)


def start_smu(smu: Keithley2600, filename, V_ds: float = 0.05):
    """Connect to the Source Measure Unit (SMU) and record values until stopped."""
    stop_event = threading.Event()

    def run_smu():
        """Run this in a thread."""
        # TODO: open file here
        # TODO: Set operating points here
        _i = 0
        while not stop_event.is_set():
            # TODO: Read time/instance, voltage, current, resistance here and record to file
            print(f"still running {_i:07} …")
            time.sleep(0.5)
            _i = _i + 1
            pass
        # TODO: Any necessary cleanup

    def stop_smu():
        """Stop the running of the SMU"""
        stop_event.set()

    worker_thread = threading.Thread(target=run_smu)
    worker_thread.start()

    return stop_smu, worker_thread

def send_and_wait_for_response(port, line, line_num = -1):
    port.write(line.encode())

    while True:
        response = port.readline().decode().strip()
        if response == "FIN":
            print(f"{line_num} | Command executed successfully.")
            break
        elif response == "ERR":
            raise Exception(f"{line_num} | Error executing command.")

def prime_wash_on_all_lines(port: serial.Serial, seconds: int = 25, rpm: int = 36):
    for channel in reversed(REAGENT_CHANNELS):
        logger.debug(f"\tChannel {channel.value:02}")
        prime_wash_to_channel(port, channel, seconds, rpm)

def prime_all_reagents(port: serial.Serial):
    for channel in reversed(REAGENT_CHANNELS):
        logger.info(f"\tChannel {channel.value:02}")
        prime_reagent_to_channel(port, channel)


def initialise_microfluidics_device(mfd_port: serial.Serial):
    logger.info("=== Initialise device ===")
    logger.info("Priming the wash line.")
    prime_wash_to_channel(mfd_port, Channel.WSHL)
    logger.info("Priming 'wash' on all reagents' lines!")
    prime_wash_on_all_lines(mfd_port)

    logger.info("Priming reagents to all channels")
    for chan in REAGENT_CHANNELS:
        logger.debug(f"\tChannel {chan.value:02}")
        prime_reagent_to_channel(mfd_port, chan)

    logger.info("Washing common line")
    wash_common(mfd_port)
    logger.info("Washing GFET line")
    wash_chip(mfd_port)

    logger.info("Venting common line")
    vent_common(mfd_port)
    logger.info("Venting GFET line")
    vent_chip2waste(mfd_port)
    logger.info("=========================")


def reset_microfluidics_device(mfd_port: serial.Serial):
    """Reset the microfluidics device."""
    logger.info("=== Reset microfluidics device ===")
    logger.info("wash common")
    wash_common(mfd_port)
    logger.info("wash GFET")
    wash_chip(mfd_port)
    logger.info("vent common")
    vent_common(mfd_port)
    logger.info("vent GFET")
    vent_chip2waste(mfd_port)
    logger.info("==================================")


def run_fluid_detection_loop(mfd_port: serial.Serial, smu: Keithley2600):
    """Run the fluid detection loop."""
    logger.info("=== Fluid detection loop ===")
    # logger.info("Begin fluid-detection loop")
    # for chan in REAGENT_CHANNELS:
    #     stop, thrd = start_smu(
    #         smu,
    #         Path(f"/tmp/signals_channel{chan.value:02}.txt"))
    #     print(f"Collecting plug for reagent {chan.value}")
    #     collect(mcf_port, chan) # collect/waste reagent plug
    #     print(f"Pushing reagent {chan.value} out to waste")
    #     vent_chip2waste(mcf_port)# vent to collection/waste
    #     stop() # stop SMU
    #     thrd.join() # Wait for graceful shutdown
    logger.info("============================")
        

def run():
    logger.info("Device selection")
    mfd_port = select_microfluidics_device_port()
    smu = connect(select_visa_address())

    initialise_microfluidics_device(mfd_port)
    run_fluid_detection_loop(mfd_port, smu)
    reset_microfluidics_device(mfd_port)

    # print("would plot values for each channel …")
    return 0


if __name__ == "__main__":
    def main():
        """Script entry pont"""
        parser = ArgumentParser("Fluid Detection")
        parser.add_argument("--output-directory",
                            type=Path,
                            default=Path("/tmp"))
        parser.add_argument("--log-level",
                            type=str,
                            choices=("critical",
                                     "error",
                                     "warning",
                                     "info",
                                     "debug"),
                            default="info")
        args = parser.parse_args()

        logger.setLevel(getattr(logging, args.log_level.upper()))
        set_loggers_level(('microfluidics',),
                          logger.getEffectiveLevel())

        return run()

    main()
