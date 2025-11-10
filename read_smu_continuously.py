import time
import signal
import logging
import argparse
from pathlib import Path

from gfet.keithley import initialise_smu
from logging_utils import set_loggers_level

logger = logging.getLogger(__name__)
logging.basicConfig(
    encoding="utf-8",
    format="%(asctime)s - %(name)s - %(levelname)s — %(message)s")

__stop_running__ = False


def sigterm_handler(signum, frame):
    """Handle a SIGTERM signal."""
    global __stop_running__
    logger.info("Received a termination signal, shutting down gracefully.")
    __stop_running__ = True


signal.signal(signal.SIGTERM, sigterm_handler)


def print_line(reading):
    """Print the reading in a line."""
    print(",".join((str(item) for item in reading)))


def read_values(
        visa_address: str,
        line_frequency: int,
        nplc: float,
        gate_voltage: float = 1.00,
        drain_voltage: float = 0.05
) -> int:
    """Read the values."""
    logger.info("Initialising the device.")
    smu = initialise_smu(visa_address, line_frequency, nplc)

    # set Operation points
    logger.debug("Setting up the operating points.")
    smu.apply_voltage(smu.smua, gate_voltage)  # set gate voltage
    smu.apply_voltage(smu.smub, drain_voltage) # set drain voltage
    logger.info("Device ready.")

    logger.debug("Begin retrieving values.")
    _keys = (
        "t",
        "drain_voltage",
        "drain_current",
        "drain_resistance",
        "gate_voltage",
        "gate_current")
    print_line(_keys)
    while not __stop_running__:
        drain_v, drain_c = (
            smu.measure_voltage(smu.smub),
            smu.measure_current(smu.smub))
        _reading = (
            time.time(),
            drain_v,
            drain_c,
            ("" if drain_c == 0.0 else abs((drain_v/drain_c)/1000)),
            smu.measure_voltage(smu.smua),
            smu.measure_current(smu.smua))
        print_line(_reading)

    logger.debug("Ending program.")
    return 0


def main():
    """smu_read_continuously entry point."""
    parser = argparse.ArgumentParser("read_smu_continuously")
    parser.add_argument(
        "--log-level",
        type=str,
        choices=("critical",
                 "error",
                 "warning",
                 "info",
                 "debug"),
        default="info")
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
    parser.add_argument(
        "--gate-voltage",
        type=float,
        default=1.00,
        help="A value for the gate voltage.")
    parser.add_argument(
        "--drain-voltage",
        type=float,
        default=0.05,
        help="A value for the gate voltage.")

    args = parser.parse_args()
    logger.setLevel(getattr(logging, args.log_level.upper()))
    set_loggers_level(("microfluidics", "gfet.keithley"),
                      logger.getEffectiveLevel())
    return read_values(
        args.smu_visa_address,
        args.line_frequency,
        args.nplc,
        args.gate_voltage,
        args.drain_voltage)


if __name__ == "__main__":
    main()
