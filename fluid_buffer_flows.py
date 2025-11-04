"""
fluid_buffer_flows: Attempt to detect change in fluid from a neutral buffer
fluid to a reagent of interest.
"""
import sys
import logging
from argparse import Namespace, ArgumentParser

from logging_utils import setup_logging
from microfluidics import REAGENT_CHANNELS

logger = logging.getLogger(__name__)
logging.basicConfig(
    encoding="utf-8",
    format="%(asctime)s - %(name)s - %(levelname)s — %(message)s")

WASH = REAGENT_CHANNELS[0]
PBS_0point001X = REAGENT_CHANNELS[3]
PBS_0point0001X = REAGENT_CHANNELS[2]
PBS_0point00001X = REAGENT_CHANNELS[1]


def dispatch_subcommand(args: Namespace):
    """Dispatch the subcommand to the appropriate function."""
    logger.info("In dispatch function: %s", __name__)
    logger.debug("We are dispatching!")
    match args.command:
        case "run-fluid-flows":
            logger.debug("Would run actual flows!")
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
