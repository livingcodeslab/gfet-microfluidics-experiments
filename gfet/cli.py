"""Command-line utilities"""
from argparse import ArgumentParser
from typing import TypeVar, Callable


def fetch_range_float(value: str) -> tuple[float, float, float]:
    """Convert a string into a tuple of values."""
    items = value.split(",")
    if len(items) not in (2, 3):
        raise ValueError(
            "Invalid range value. Expected two comma-separated values.")

    items = tuple(float(item) for item in items)
    if len(items) == 2:
        items = items + (0.1,)
    if items[0] < items[1]:
        return items
    return (items[1], items[0], items[2])


T = TypeVar("T")
def make_value_range_checker(
        low: T, high: T, title: str = "") -> Callable[[str], T]:
    """Return a function that verifies that the value is is given is within the
    range [low, high]."""
    assert type(low) == type(high), (
        "Both `low` and `high` **MUST** be of the same type.")
    def _checker_(val) -> T:
        _val = type(low)(val)
        if low <= _val <= high:
            return _val
        raise ValueError(
            (f"{title.strip()}: " if bool(title.strip()) else "") +
            f"{_val} is not within [{low}, {high}].")
    return _checker_


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
