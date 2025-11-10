"""
fluid_buffer_flows: Attempt to detect change in fluid from a neutral buffer
fluid to a reagent of interest.
"""
import sys
import time
import logging
from argparse import Namespace, ArgumentParser

import serial

from logging_utils import setup_logging
from microfluidics import (collect, wash_chip, REAGENT_CHANNELS)

logger = logging.getLogger(__name__)

WASH = REAGENT_CHANNELS[0]
PBS_0point001X = REAGENT_CHANNELS[2]
PBS_0point0005X = REAGENT_CHANNELS[1]


def run_fluid_buffer_flows(mfd_port: serial.Serial) -> int:
    """Run flows, picking reagent and buffering them with neutral wash."""
    logger.info("Begin fluid-buffer flows.")
    for chan in (PBS_0point00001X, PBS_0point0001X, PBS_0point001X):
        PLUG_SIZE = 5
        logger.info("Collecting reagent %02d for %02d seconds.",
                    chan.value,
                    PLUG_SIZE)
        collect(mfd_port, chan, seconds=PLUG_SIZE)
        logger.info("Buffering with %02d seconds long wash buffer",
                    PLUG_SIZE*2)
        wash_chip(mfd_port, seconds=(2 * PLUG_SIZE))

    logger.info("Washing GFET line for %02d seconds.", 60)
    wash_chip(mfd_port, seconds=60)
    logger.info("Complete fluid-buffer flows.")
    return 0


def dispatch_subcommand(args: Namespace):
    """Dispatch the subcommand to the appropriate function."""
    logger.info("In dispatch function: %s", __name__)
    logger.debug("We are dispatching!")
    match args.command:
        case "run-fluid-flows":
            return run_fluid_buffer_flows(serial.Serial(
                args.microfluidics_serial_port))
    return 0


if __name__ == "__main__":
    def run() -> int:
        """This is the entry-point t othe fluid_buffer_flows script."""
        parser = ArgumentParser("fluid_buffer_flows")
        parser.add_argument("--log-level",
                            type=str,
                            choices=("critical",
                                     "error",
                                     "warning",
                                     "info",
                                     "debug"),
                            default="info")

        subcommands = parser.add_subparsers(
            dest='command',
            help='Available commands',
            required=True)

        run_flows = subcommands.add_parser(
            "run-fluid-flows",
            description="Run the fluid flows in the system.")
        run_flows.add_argument(
            "--microfluidics-serial-port",
            type=str,
            default="/dev/ttyACM0",
            help=(
                "The serial port path to the system device that grants access "
                "to the microfluidics device. Default (/dev/ttyACM0)"))
        run_flows.add_argument(
            "--smu-visa-address",
            type=str,
            default="ASRL/dev/ttyUSB0::INSTR",
            help=(
                "The VISA address to the source-measure unit. "
                "Default (ASRL/dev/ttyUSB0::INSTR)"))
        args = parser.parse_args()
        setup_logging(args.log_level, logger, ("microfluidics",))
        return dispatch_subcommand(args)
    sys.exit(run())
