"""
fluid_detection: Attempt to detect when a liquid passes over chip.

This flows a 'plug' of fluid, surrounded by air, over the chip, and is meant to
detect when the plug arrives on and depart from the chip.
"""
import logging
import threading
from pathlib import Path
from argparse import ArgumentParser

import pyvisa
from pygnuplot import gnuplot
import serial.tools.list_ports
from keithley2600 import Keithley2600

from gdnasynth.generic import write_results
from gdnasynth.keithley import initialise_smu
from gdnasynth.microfluidics import (
    collect,
    REAGENT_CHANNELS,
    vent_chip2collection,
    prime_wash_to_channel,
    prime_reagent_to_channel,
    reset_microfluidics_device,
    initialise_microfluidics_device)

from logging_utils import set_loggers_level

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


def list_visa_addresses():
    """Show a list of all VISA addresses on the computer."""
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

    def stop_smu():
        """Stop the running of the SMU"""
        stop_event.set()

    worker_thread = threading.Thread(target=run_smu)
    worker_thread.start()

    return stop_smu, worker_thread

def send_and_wait_for_response(port, line, line_num = -1):
    """Send command to microfluidics device and wait for response."""
    port.write(line.encode())

    while True:
        response = port.readline().decode().strip()
        if response == "FIN":
            print(f"{line_num} | Command executed successfully.")
            break
        if response == "ERR":
            raise Exception(# pylint: disable=[broad-exception-raised]
                f"{line_num} | Error executing command.")

def prime_all_reagents(port: serial.Serial):
    """Prime all reagent lines."""
    for channel in reversed(REAGENT_CHANNELS):
        logger.info("\tChannel %02s", channel.value)
        prime_reagent_to_channel(port, channel)


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
    return 0


def plot_file(# pylint: disable=[too-many-arguments, too-many-positional-arguments]
        infile: Path,
        outfile: Path,
        plottitle: str,
        xaxis: str,
        yaxis: str,
        ylabel: str,
        legend_title: str = "Resistance"
):
    """Create plot using data in provided file."""
    g = gnuplot.Gnuplot(log=True)
    g.set(terminal=(
        'svg font "arial,10" fontscale 1.0 size 1200,1000 dynamic background '
        'rgb "white"'),
          #terminal='pngcairo font "arial,10" fontscale 1.0 size 1000, 800',
          # output='"testplot.1.png"',
          output=f'"{outfile}"',
          key=("fixed left top horizontal Right noreverse enhanced autotitle "
               "box lt black linewidth 1.000 dashtype solid"),
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
        f"using '{xaxis}':'{yaxis}' "
        f"title '{legend_title}' "
        "with lines"]
    g.plot(*plot_args)


def dispatch_subcommand(args) -> int:
    """Dispatch the correct sub-command"""
    logger.debug("Command-line Arguments: %s", args)
    match args.command:
        case "list-serial-ports":
            list_serial_ports(args.show_all)
        case "list-visa-addresses":
            list_visa_addresses()
        case "initialise-microfluidics-device":
            initialise_microfluidics_device(
                serial.Serial(args.microfluidics_serial_port))
        case "reset-microfluidics-device":
            reset_microfluidics_device(
                serial.Serial(args.microfluidics_serial_port))
        case "initialise-source-measure-unit":
            initialise_smu(
                args.smu_visa_address,
                args.line_frequency,
                ((0.001 + 25) / 2) # halfway between
            )
        case "plot-file":
            plot_file(args.inputfile,
                      args.outputfile,
                      args.plottitle,
                      args.xaxis,
                      args.yaxis,
                      args.ylabel,
                      args.legend_title)
        case "run-fluid-detection":
            return run_fluid_detection_loop(
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

        list_visa = subcommands.add_parser(
            "list-visa-addresses",
            description="List the VISA addresse available on the system")
        list_visa.add_argument(
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

        reset_mfd = subcommands.add_parser(
            "reset-microfluidics-device",
            description="Reset device to return it to a sane state.")
        reset_mfd.add_argument(
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
        plotter.add_argument(
            "--legend_title",
            metavar="--legend-title",
            type=str,
            default="Resistance",
            help="Label for the legend in the plot.")

        args = parser.parse_args()
        logger.setLevel(getattr(logging, args.log_level.upper()))
        set_loggers_level(('microfluidics',),
                          logger.getEffectiveLevel())

        return dispatch_subcommand(args)

    main()
