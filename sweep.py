"""Do a single sweep of values. This assumes there's a fluid on the chip."""
import sys
import csv
import logging
from argparse import Namespace, ArgumentParser, ArgumentDefaultsHelpFormatter

from keithley2600 import Keithley2600

from gdnasynth.generic import float_range
from gdnasynth.logging import setup_logging
from gdnasynth.keithley import initialise_smu
from gdnasynth.cli.options import cli_add_smu_args, cli_add_logging_arg
from gdnasynth.cli.validators import (
    fetch_range_float,
    make_value_range_checker)

from isswisafre import take_reading

logger = logging.getLogger()


def sweep(
        smu: Keithley2600,
        gate_voltages: tuple[float, ...],
        drain_voltages: tuple[float, float]
) -> int:
    """Run the sweep."""
    for gvtg in gate_voltages:
        for dvtg in drain_voltages:
            yield take_reading(smu, gvtg, dvtg)
    # turn off SMU after **ALL** readings are taken.
    smu.smua.source.output = smu.smua.OUTPUT_OFF
    smu.smub.source.output = smu.smub.OUTPUT_OFF


def run_sweep(args: Namespace) -> int:
    """Run the sweep function."""
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=("timestamp",
                    "provided_gate_voltage",
                    "provided_channel_voltage",
                    "drain_voltage",
                    "drain_current",
                    "measured_gate_voltage",
                    "measured_gate_current"))
    writer.writeheader()
    for row in sweep(
            initialise_smu(args.smu_visa_address,
                           args.line_frequency,
                           args.nplc),
            tuple(float_range(
                -abs(args.gate_voltage),
                abs(args.gate_voltage),
                args.sweep_interval)),
            (args.channel_voltage, -args.channel_voltage)):
        writer.writerow(row)

    return 0


if __name__ == "__main__":
    def main():
        """sweep: entry-point function."""
        parser = cli_add_smu_args(cli_add_logging_arg(ArgumentParser(
            "sweep",
            description=(
                "Run a single sweep of the gate voltage while recording the "
                "drain-source values."),
            formatter_class=ArgumentDefaultsHelpFormatter)))
        parser.add_argument(
            "--gate_voltage",
            "--gate-voltage",
            "--gatevoltage",
            metavar="GATE-VOLTAGE",
            type=make_value_range_checker(0.1, 1.0, "Gate Voltage"),
            default=1.0,
            help=("The gate voltage to use for the sweep. The script will "
                  "sweep from -(|GATE-VOLTAGE|) to +(|GATE-VOLTAGE|)."))
        parser.add_argument(
            "--sweep_interval",
            "--sweep-interval",
            "--sweepinterval",
            metavar="SWEEP-INTERVAL",
            type=make_value_range_checker(0.00005, 0.1, "Gate Voltage"),
            default=0.01,
            help=("The gate voltage to use for the sweep. The script will "
                  "sweep from -(|GATE-VOLTAGE|) to +(|GATE-VOLTAGE|)."))
        parser.add_argument(
            "--channel-voltage",
            type=make_value_range_checker(0.000005, 0.1, "Channel Voltage"),
            default=0.05,
            help=("The absolute voltage (in volts) to apply at the channel."))
        args = parser.parse_args()
        setup_logging(args.log_level, logger)
        return run_sweep(args)

    sys.exit(main())
