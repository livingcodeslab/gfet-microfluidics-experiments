import sys
import csv
import copy
import time
import logging
import threading
from pathlib import Path
from typing import Optional
from argparse import Namespace, ArgumentParser

import pyvisa
from pygnuplot import gnuplot
import serial.tools.list_ports
from keithley2600 import Keithley2600

from gfet.generic import write_results
from gfet.keithley import connect, select_visa_address, device_stabilisation

from logging_utils import set_loggers_level
from microfluidics import (collect,
                           Channel,
                           wash_chip,
                           wash_common,
                           vent_common,
                           vent_chip2waste,
                           REAGENT_CHANNELS,
                           vent_chip2collection,
                           prime_wash_to_channel,
                           prime_reagent_to_channel)

logger = logging.getLogger(__name__)
logging.basicConfig(
    encoding="utf-8",
    format="%(asctime)s - %(name)s - %(levelname)s — %(message)s")


def list_serial_ports(show_all: bool = False):
    """Print out a list of serial ports."""
    headings = ("Path", "Details")
    print(f"{headings[0]:20}\t{headings[1]}")
    ports = serial.tools.list_ports.comports()
    if not show_all:
        ports = [port for port in ports
                 if any((port.product, port.manufacturer, port.vid, port.pid))]
    for port in ports:
        print(
            f"{port.device:20}\t{port.manufacturer}:"
            f"{port.product} ({port.vid}:{port.pid})")


def list_visa_addresses(show_all: bool = False):
    resources = pyvisa.ResourceManager().list_resources()
    print("The available VISA addresses are: ")
    for address in resources:
        print(address)


def start_smu(
        smu: Keithley2600,
        filepath: Path,
        drain_voltage: float = 0.05,
        gate_voltage: float = 1.00
):
    """Connect to the Source Measure Unit (SMU) and record values until stopped."""
    stop_event = threading.Event()

    # Operation points
    smu.apply_voltage(smu.smua, gate_voltage)  # set gate voltage
    smu.apply_voltage(smu.smub, drain_voltage) # set drain voltage
    # ================= #

    def run_smu():
        """Run this in a thread."""
        _i = 0
        _results = []
        while not stop_event.is_set():
            drain_v, drain_c = (
                smu.measure_voltage(smu.smub),
                smu.measure_current(smu.smub))
            _reading = {
                "t": _i,
                "drain_voltage": drain_v,
                "drain_current": drain_c,
                "drain_resistance": (
                    "" if drain_c == 0.0 else abs((drain_v/drain_c)/1000)),
                "gate_voltage": smu.measure_voltage(smu.smua),
                "gate_current": smu.measure_current(smu.smua),
            }
            _results.append(_reading)
            _i = _i + 1

            write_results(filepath, _results)

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


def run_fluid_detection_loop(
        mfd_port: serial.Serial,
        smu: Keithley2600,
        output_directory: Path):
    """Run the fluid detection loop."""
    logger.info("=== Fluid detection loop ===")
    output_directory.mkdir(exist_ok=True)
    for chan in REAGENT_CHANNELS:
        stop, thrd = start_smu(
            smu,
            output_directory.joinpath(f"{chan.value:02}.txt"))
        logger.info("Collecting plugs for reagent %s", chan.value)
        vent_chip2collection(mfd_port, seconds=120)
        for _ in range(0, 5):
            collect(mfd_port, chan, seconds=5)
            vent_chip2collection(mfd_port, seconds=1)

        logger.info("Push solid reagent %s flow out to waste", chan.value)
        collect(mfd_port, chan, seconds=90)
        logger.info("Venting the GFET line completely")
        vent_chip2collection(mfd_port, seconds=120)# vent to collection/waste
        stop() # stop SMU
        thrd.join() # Wait for graceful shutdown
    logger.info("============================")
        

def run(
        mfd_port: serial.Serial,
        smu: Keithley2600,
        outdir: Path
) -> int:
    """Run the fluid-detection logic."""
    run_fluid_detection_loop(mfd_port, smu, outdir)
    reset_microfluidics_device(mfd_port)

    # print("would plot values for each channel …")
    return 0


def init_smu(visa_address, line_frequency):
    """Initialize the Source-Measure Unit device."""
    smu = Keithley2600(visa_address)

    device_stabilisation(smu)

    integration_time = (0.001 + (1 / line_frequency)) / 2 # halfway between
    smu.set_integration_time(smu.smua, integration_time)
    smu.set_integration_time(smu.smub, integration_time)


def plot_file(infile, outfile, plottitle, yaxis, ylabel):
    g = gnuplot.Gnuplot(log=True)
    g.set(terminal='svg font "arial,10" fontscale 1.0 size 1200,1000 dynamic background rgb "white"',
          #terminal='pngcairo font "arial,10" fontscale 1.0 size 1000, 800',
          # output='"testplot.1.png"',
          output=f'"{outfile}"',
          key="fixed left top horizontal Right noreverse enhanced autotitle box lt black linewidth 1.000 dashtype solid",
          # samples="50, 50",
          title=f'"{plottitle}" font ",20" textcolor lt -1 norotate',
          datafile='separator ","',
          # xtics=0.005,
          xrange='[* : *] noreverse writeback',
          # x2range='[* : *] noreverse writeback',
          yrange='[* : *] noreverse writeback',
          # y2range='[* : *] noreverse writeback',
          zrange='[* : *] noreverse writeback',
          cbrange='[* : *] noreverse writeback',
          rrange='[* : *] noreverse writeback',
          colorbox='vertical origin screen 0.9, 0.2 size screen 0.05, 0.6 front noinvert bdefault',
          xlabel='"Time"',
          ylabel=f'"{ylabel}" rotate')

    g.cmd("NO_ANIMATION = 1")
    plot_args = [
        f"'{infile}' "
        f"using 't':'{yaxis}' "
        f"title 'some title' "
        "with lines"]
    g.plot(*plot_args)


def dispatch_subcommand(args) -> int:
    """Dispatch the correct sub-command"""
    logger.debug("Command-line Arguments: %s", args)
    match args.command:
        case "list-serial-ports":
            list_serial_ports(args.show_all)
        case "list-visa-addresses":
            list_visa_addresses(args.show_all)
        case "initialise-microfluidics-device":
            initialise_microfluidics_device(
                serial.Serial(args.microfluidics_serial_port))
        case "initialise-source-measure-unit":
            init_smu(args.smu_visa_address, args.line_frequency)
        case "plot-file":
            plot_file(args.inputfile,
                      args.outputfile,
                      args.plottitle,
                      args.yaxis,
                      args.ylabel)
        case "run-fluid-detection":
            return run(
                serial.Serial(args.microfluidics_serial_port),
                Keithley2600(args.smu_visa_address),
                args.output_directory)

    return 0


if __name__ == "__main__":
    def main():
        """Script entry pont"""
        parser = ArgumentParser("fluid_detection")
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

        list_serial = subcommands.add_parser(
            "list-serial-ports",
            description="List the serial ports available on the system")
        list_serial.add_argument(
            "--show-all",
            help=("We show only serial ports with vendor ID values by default. "
                  "To see all ports, pass this flag."),
            action="store_true")

        list_visa_addresses = subcommands.add_parser(
            "list-visa-addresses",
            description="List the VISA addresse available on the system")
        list_visa_addresses.add_argument(
            "--show-all",
            help=("We show only VISA addresses with actual devices attached. "),
            action="store_true")

        run_fluid_detection = subcommands.add_parser(
            "run-fluid-detection",
            description="List the VISA addresse available on the system")
        run_fluid_detection.add_argument(
            "--microfluidics-serial-port",
            type=str,
            default="/dev/ttyACM0",
            help=(
                "The serial port path to the system device that grants access "
                "to the microfluidics device. Default (/dev/ttyACM0)"))
        run_fluid_detection.add_argument(
            "--smu-visa-address",
            type=str,
            default="ASRL/dev/ttyUSB0::INSTR",
            help=(
                "The VISA address to the source-measure unit. "
                "Default (ASRL/dev/ttyUSB0::INSTR)"))
        run_fluid_detection.add_argument(
            "output_directory",
            type=Path,
            metavar="output-directory",
            help=("Output directory where this program will put the results "
                  "files."))

        init_mfd = subcommands.add_parser(
            "initialise-microfluidics-device",
            description=(
                "Run initialisation on microfluidics device to ensure it is in "
                "a usable state."))
        init_mfd.add_argument(
            "--microfluidics-serial-port",
            type=str,
            default="/dev/ttyACM0",
            help=(
                "The serial port path to the system device that grants access "
                "to the microfluidics device. Default (/dev/ttyACM0)"))

        init_smu = subcommands.add_parser(
            "initialise-source-measure-unit",
            description=(
                "Run initialisation on the Source-Measure Unit device to ensure"
                "it is in a usable state."))
        init_smu.add_argument(
            "--line-frequency",
            type=int,
            choices=(50, 60),
            default=60)
        init_smu.add_argument(
            "--smu-visa-address",
            type=str,
            default="ASRL/dev/ttyUSB0::INSTR",
            help=(
                "The Virtual Instument Software Architecture (VISA) address "
                "to connect to the source-measure unit."))

        plotter = subcommands.add_parser(
            "plot-file",
            description="Produce plot of data in file.")
        plotter.add_argument(
            "inputfile",
            type=Path,
            help="Path to file with data to plot")
        plotter.add_argument(
            "outputfile",
            type=Path,
            help="Path to output plot")
        plotter.add_argument(
            "--plottitle",
            type=str,
            help="A name for your plot.",
            default="Fluid Detection: Resistance Characteristics")
        plotter.add_argument(
            "--xaxis",
            type=str,
            help="Field in file to use as X axis",
            default="t")
        plotter.add_argument(
            "--xlabel",
            type=str,
            help="Label for X axis",
            default="Time")
        plotter.add_argument(
            "--yaxis",
            type=str,
            help="Field in file to use as Y axis",
            default="drain_resistance")
        plotter.add_argument(
            "--ylabel",
            type=str,
            help="Label for Y axis",
            default="Drain Resistance (Ω)")

        args = parser.parse_args()
        logger.setLevel(getattr(logging, args.log_level.upper()))
        set_loggers_level(('microfluidics',),
                          logger.getEffectiveLevel())

        return dispatch_subcommand(args)

    main()
