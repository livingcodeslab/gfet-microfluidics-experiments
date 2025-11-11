"""
isswisafre: intermittent start/stop with sweeping and flipping reads

Sweep gate voltage from some minimum to some maximum, taking two readings at
each point in the sweep (one for positive channel voltage and one for negative
channel voltage.).

The microfluidics device is stopped while taking the reading, and the SMU
channels are turned off while the microfluidics device is running.
"""
import sys
import csv
import time
import logging
import argparse
from typing import Callable, Iterator

import serial
from keithley2600 import Keithley2600

from gfet.generic import float_range2
from gfet.keithley import initialise_smu
from gfet.cli import (cli_add_smu_args,
                      cli_add_logging_arg,
                      make_value_range_checker,
                      cli_add_microfluidics_args)
from gfet.microfluidics import Channel, collect, wash_chip


from logging_utils import setup_logging

logger = logging.getLogger(__name__)

WASH = Channel.WSHL
PBS_0POINT001X = Channel.CH02
PBS_0POINT0005X = Channel.CH01


def take_reading(
        smu: Keithley2600,
        gate_voltage: float,
        channel_voltage: float
) -> dict[str, float]:
    """Sweep gate voltage from `gv_low` to `gv_high` and take readings."""
    # Set gate woltage
    smu.apply_voltage(smu.smua, gate_voltage)
    # Set channel voltage to `chn_voltage`
    smu.apply_voltage(smu.smub, channel_voltage)
    # take readings
    # smu.smua.source.output = smu.smua.OUTPUT_OFF
    # smu.smub.source.output = smu.smub.OUTPUT_OFF
    reading = dict(zip(
        ("timestamp",
         "provided_gate_voltage",
         "provided_channel_voltage",
         "drain_voltage",
         "drain_current",
         "measured_gate_voltage",
         "measured_gate_current"),
        (time.time(),
         gate_voltage,
         channel_voltage,
         smu.measure_voltage(smu.smub),
         smu.measure_current(smu.smub),
         smu.measure_voltage(smu.smua),
         smu.measure_current(smu.smua))))
    # Turn off SMU channels
    smu.smua.source.output = smu.smua.OUTPUT_OFF
    smu.smub.source.output = smu.smub.OUTPUT_OFF
    return reading


def pump_and_read(
        smu: Keithley2600,
        command: Callable[[int], bool],
        seconds: int,
        gate_voltages: tuple[float, ...],
        channel_voltages: tuple[float, float]
) -> Iterator[dict[str, float]]:
    """Pump from channel and read voltage and current values."""
    logger.debug("There are %s gate voltages.", len(gate_voltages))
    logger.debug("There are %s channel voltages.", len(channel_voltages))
    while seconds > 0:
        command(seconds=1)
        logger.debug("remaining seconds for this run: %s", seconds)
        for gatevtg in gate_voltages:
            logger.debug("gate voltage: %s", gatevtg)
            for chnvtg in channel_voltages:
                logger.debug("channel voltage: %s", chnvtg)
                yield take_reading(smu, gatevtg, chnvtg)
        logger.debug("recomputing seconds...")
        seconds = seconds - 1
        logger.debug("New seconds value: %s", seconds)


def run_pattern(
        smu: Keithley2600,
        pattern: tuple[tuple[Callable[[int], bool], int], ...],
        gate_voltages: tuple[float, ...],
        channel_voltage: float
) -> Iterator[dict[str, float]]:
    """Run pattern of flows and take readings."""
    for item in pattern:
        yield from pump_and_read(
                smu,
                command=item[0],
                seconds=item[1],
                gate_voltages=gate_voltages,
                channel_voltages=(channel_voltage, -channel_voltage))


def run(args: argparse.Namespace) -> int:
    """Run the experiment."""
    # init mfd, smu, ...
    smu = initialise_smu(args.smu_visa_address, args.line_frequency, args.nplc)
    mfd = serial.Serial(args.microfluidics_serial_port)
    # init channels
    _pattern = (
        (lambda seconds: collect(port=mfd,
                                 channel=PBS_0POINT0005X,
                                 seconds=seconds,
                                 rpm=36),
         10),
        (lambda seconds: wash_chip(port=mfd,
                                   seconds=seconds,
                                   rpm=36),
         10),
        (lambda seconds: collect(port=mfd,
                                 channel=PBS_0POINT001X,
                                 seconds=seconds,
                                 rpm=36),
         10),
        (lambda seconds: wash_chip(port=mfd,
                                   seconds=seconds,
                                   rpm=36),
         120))
    _values = run_pattern(
        smu,
        _pattern,
        tuple(float_range2(0.0, args.max_gate_voltage, 100)),
        args.channel_voltage)

    _writer = csv.DictWriter(
        sys.stdout,
        fieldnames=("timestamp",
                    "provided_gate_voltage",
                    "provided_channel_voltage",
                    "drain_voltage",
                    "drain_current",
                    "measured_gate_voltage",
                    "measured_gate_current"))
    _writer.writeheader()
    for _value in _values:
        _writer.writerow(_value)

    return 0


def main():
    """SMU: read with sweeping gate and flipping channel voltage."""
    parser = cli_add_microfluidics_args(
        cli_add_smu_args(
            cli_add_logging_arg(
                argparse.ArgumentParser(
                    "isswisafre"))))
    parser.add_argument(
        "--max-gate-voltage",
        type=make_value_range_checker(-1.0, 1.0, "Gate Voltage"),
        default=1.0,
        help="Voltage (in volts) to apply at the gate terminals. Unit ")
    parser.add_argument(
        "--channel-voltage",
        type=make_value_range_checker(0.0, 0.1, "Channel Voltage"),
        default=0.05,
        help=(
            "The absolute voltage (in volts) to apply at the channel. This "
            "value will be flipped from positive to negative and back, several "
            "times during the running of this script."))
    args = parser.parse_args()
    setup_logging(args.log_level, logger, ("gfet.cli",
                                           "gfet.generic",
                                           "gfet.generic",
                                           "gfet.keithley",
                                           "gfet.microfluidics"))
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
