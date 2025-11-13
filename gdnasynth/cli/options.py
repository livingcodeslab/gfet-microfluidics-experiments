"""Command-line utilities"""
from argparse import ArgumentParser


def cli_add_logging_arg(parser: ArgumentParser) -> ArgumentParser:
    """Add --log-level option to the CLI"""
    parser.add_argument(
        "--log-level",
        "--loglevel",
        type=str,
        choices=("critical",
                 "error",
                 "warning",
                 "info",
                 "debug"),
        default="info")
    return parser


def cli_add_smu_args(parser: ArgumentParser) -> ArgumentParser:
    """Add basic SMU initialisation options to the CLI."""
    parser.add_argument(
        "--smu-visa-address",
        type=str,
        default="ASRL/dev/ttyUSB0::INSTR",
        help=(
            "The VISA address to the source-measure unit. "
            "Default (ASRL/dev/ttyUSB0::INSTR)"))
    parser.add_argument(
        "--line-frequency",
        type=int,
        choices=(50, 60),
        default=60,
        help="The AC line frequency.")
    parser.add_argument(
        "--nplc",
        type=float,
        default=((0.001 + 25)/2),
        help="Number of power-line cycles: used for measurement integration.")
    return parser


def cli_add_microfluidics_args(parser: ArgumentParser) -> ArgumentParser:
    """Add the microfluidics options to the CLI."""
    parser.add_argument(
        "--microfluidics-serial-port",
        type=str,
        default="/dev/ttyACM0",
        help=(
            "The serial port path to the system device that grants access "
            "to the microfluidics device. Default (/dev/ttyACM0)"))
    return parser
