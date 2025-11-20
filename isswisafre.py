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
from pathlib import Path
from typing import Callable, Iterator

import serial
from keithley2600 import Keithley2600

from gdnasynth.generic import float_range
from gdnasynth.logging import setup_logging
from gdnasynth.keithley import initialise_smu
from gdnasynth.microfluidics import Channel, collect, wash_chip
from gdnasynth.cli.validators import (
    existing_file,
    existing_directory,
    make_value_range_checker)
from gdnasynth.cli.options import (
    cli_add_smu_args,
    cli_add_logging_arg,
    cli_add_microfluidics_args)

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
    _counter = 0
    while _counter < seconds:
        command(1)
        logger.debug("remaining seconds for this run: %s", seconds-_counter)
        for gatevtg in gate_voltages:
            logger.debug("gate voltage: %s", gatevtg)
            for chnvtg in channel_voltages:
                logger.debug("channel voltage: %s", chnvtg)
                yield take_reading(smu, gatevtg, chnvtg)

        # Turn off SMU channels
        smu.smua.source.output = smu.smua.OUTPUT_OFF
        smu.smub.source.output = smu.smub.OUTPUT_OFF
        logger.debug("recomputing seconds...")
        _counter = _counter + 1
        logger.debug("New seconds value: %s", seconds)


def run_pattern(
        smu: Keithley2600,
        pattern: tuple[str, tuple[Callable[[int], bool], int], ...],
        gate_voltages: tuple[float, ...],
        channel_voltage: float
) -> Iterator[dict[str, float]]:
    """Run pattern of flows and take readings."""
    for item in pattern:
        logger.info("Running '%s' for %02d seconds.", item[0], item[2])
        yield from pump_and_read(
                smu,
                command=item[1],
                seconds=item[2],
                gate_voltages=gate_voltages,
                channel_voltages=(channel_voltage, -channel_voltage))


def run_experiment(args: argparse.Namespace) -> int:
    """Run the experiment."""
    # init mfd, smu, ...
    smu = initialise_smu(args.smu_visa_address, args.line_frequency, args.nplc)
    mfd = serial.Serial(args.microfluidics_serial_port)
    # init channels
    _pattern = (
        ("0.0005X PBS",
         lambda seconds: collect(port=mfd,
                                 channel=PBS_0POINT0005X,
                                 seconds=seconds,
                                 rpm=36),
         10),
        ("Distilled Water",
         lambda seconds: wash_chip(port=mfd,
                                   seconds=seconds,
                                   rpm=36),
         10),
        ("0.001X PBS",
         lambda seconds: collect(port=mfd,
                                 channel=PBS_0POINT001X,
                                 seconds=seconds,
                                 rpm=36),
         10),
        ("Distilled Water",
         lambda seconds: wash_chip(port=mfd,
                                   seconds=seconds,
                                   rpm=36),
         120))
    _values = run_pattern(
        smu,
        _pattern,
        tuple(float_range(0.0, args.max_gate_voltage, 0.001)),
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


def __genfilename__(outdir, source, middle):
    return outdir.joinpath(f"{source.stem}_{middle}{source.suffix}")


def process_data(args: argparse.Namespace) -> int:
    """Process the raw data into useful data."""
    srcpath = args.raw_source_file
    outdir = args.output_directory
    with (open(srcpath, encoding="utf8") as source,
          open(__genfilename__(outdir, srcpath, "positive"),
               "w",
               encoding="utf8") as positivefile,
          open(__genfilename__(outdir, srcpath, "negative"),
               "w",
               encoding="utf8") as negativefile):
        _reader = csv.DictReader(source)
        _poswriter = csv.DictWriter(
            positivefile, fieldnames=_reader.fieldnames, dialect="unix")
        _poswriter.writeheader()
        _negwriter = csv.DictWriter(
            negativefile, fieldnames=_reader.fieldnames, dialect="unix")
        _negwriter.writeheader()
        for _line in _reader:
            if float(_line["drain_voltage"]) < 0:
                _negwriter.writerow(_line)
            else:
                _poswriter.writerow(_line)


def dispatch_subcommand(args) -> int:
    """Dispatch to the appropriate function."""
    match args.command:
        case "run-experiment":
            return run_experiment(args)
        case "process-data":
            return process_data(args)
    return 2


def main():
    """SMU: read with sweeping gate and flipping channel voltage."""
    parser = cli_add_logging_arg(argparse.ArgumentParser("isswisafre"))
    subcommands = parser.add_subparsers(dest="command", required=True)

    run_expt_parser = cli_add_microfluidics_args(cli_add_smu_args(
        subcommands.add_parser(
            "run-experiment", description="Run the experiment")))
    run_expt_parser.add_argument(
        "--max-gate-voltage",
        type=make_value_range_checker(-1.0, 1.0, "Gate Voltage"),
        default=1.0,
        help="Voltage (in volts) to apply at the gate terminals. Unit ")
    run_expt_parser.add_argument(
        "--channel-voltage",
        type=make_value_range_checker(0.0, 0.1, "Channel Voltage"),
        default=0.05,
        help=(
            "The absolute voltage (in volts) to apply at the channel. This "
            "value will be flipped from positive to negative and back, several "
            "times during the running of this script."))

    data_processing_parser = subcommands.add_parser(
        "process-data",
        description="Run various data processing tasks against raw results.")
    data_processing_parser.add_argument(
        "raw_source_file",
        metavar="raw-source-file",
        type=existing_file,
        help=("Path to file with raw results from running this script with the "
              "'run-experiment' option."))
    data_processing_parser.add_argument(
        "output_directory",
        metavar="output-directory",
        type=existing_directory,
        help="Path to directory where the processed files will be saved.")

    args = parser.parse_args()
    setup_logging(args.log_level, logger, ("gfet.cli",
                                           "gfet.generic",
                                           "gfet.generic",
                                           "gfet.keithley",
                                           "gfet.microfluidics"))
    return dispatch_subcommand(args)


if __name__ == "__main__":
    sys.exit(main())
