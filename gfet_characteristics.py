"""GFET Characteristics code."""
import csv
import logging
from pathlib import Path
from argparse import ArgumentParser

from keithley2600 import Keithley2600

from gfet.generic import float_range
from gfet.keithley import connect, select_visa_address
from gfet.generic import float_range, range_length, build_filename

_module_name_ = __name__
logger = logging.getLogger(__name__)
logHandler = logging.StreamHandler()
logHandler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s — %(message)s"))
logger.addHandler(logHandler)
logger.setLevel(logging.WARNING)

def set_loggers_level(loggers, loglevel):
    for logger_str in loggers:
        logging.getLogger(logger_str).setLevel(loglevel)


def write_results(filepath: Path, results: tuple[dict, ...]):
    # TODO: remove these debug statements
    logger.debug("Fieldnames: %s", list(results[0].keys()))
    # END: TODO: remove these debug statements
    with filepath.open("w") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)


def perform_experiment(
        inst: Keithley2600,
        outdir: Path,
        file_prefix: str,
        line_frequency: int
):
    # TODO: Do at least 3 readings for at least one of the FETs to stabilise the
    # chip.
    #
    # == Water Specifications ==
    # Minimum theoretical voltage needed to crack water: 1.23 V
    # Minimum practical voltage needed to crack water: 1.5 V
    #
    # == GFET Specifications ==
    # Dirac point (liquid gating in PBS): <1V
    # Maximum gate-source voltage (back gating): ±50V
    # Maximum gate-source voltage (liquid gating in PBS): ±2V
    #
    # == SMU Specifications ==
    # -1V to 1V: Range is 2V, resolution 50μV
    # Integration time:
    #   - between 0.001 and 25*(1/{line-frequency})
    #   - Higher value == more accurate results, lower speed
    #   - Lower value == less accurate results, higher speed
    integration_time = (0.001 + (1 / line_frequency)) / 2 # halfway between
    inst.set_integration_time(inst.smua, integration_time)
    inst.set_integration_time(inst.smub, integration_time)
    # for idx, gate_voltage in enumerate(float_range(-1, 1, 0.001), start=1):
    for idx, gate_voltage in enumerate(float_range(-1, 1, 0.1), start=1):
        inst.apply_voltage(inst.smua, gate_voltage)
        results = tuple()
        # for drain_voltage in float_range(-1, 1, 0.00005):
        for drain_voltage in float_range(-1, 1, 0.005):
            inst.apply_voltage(inst.smub, drain_voltage)
            results = results + ({
                "x_axis": f"{drain_voltage:0.3}",
                "gate_voltage": inst.measure_voltage(inst.smua),
                "gate_current": inst.measure_current(inst.smua),
                "drain_voltage": inst.measure_voltage(inst.smub),
                "drain_current": inst.measure_current(inst.smub)
            },)

        write_results(build_filename(outdir, file_prefix, idx), results)

    return 0

if __name__ == "__main__":
    def main():
        parser = ArgumentParser("GFET Characteristics")
        parser.add_argument(
            "visa_address",
            type=str,
            help=(
                "A Virtual Instrument Software Architecture (VISA) address e.g."
                " 'TCPIP0::169.254.0.1::inst0::INSTR'."))
        parser.add_argument("--output-directory",
                            type=Path,
                            default=Path(
                                "./GFET_Characteristics_results").absolute())
        parser.add_argument("--file-prefix",
                            type=str,
                            default="result")
        parser.add_argument("--connection-retries",
                            type=int,
                            default=3)
        parser.add_argument("--log-level",
                            type=str,
                            choices=("critical",
                                     "error",
                                     "warning",
                                     "info",
                                     "debug"),
                            default="warning")
        parser.add_argument("--line-frequency",
                            type=int,
                            choices=(50, 60),
                            default=60)
        args = parser.parse_args()

        logger.setLevel(
            logging.getLevelNamesMapping()[args.log_level.upper()])
        set_loggers_level(
            (_module_name_, "keithley2600.keithley_driver", "keithley_utils"),
            logger.getEffectiveLevel())
        logger.debug(f"ARGS: %s", args)
        return perform_experiment(connect(args.visa_address,
                                          retries=args.connection_retries),
                                  args.output_directory,
                                  args.file_prefix,
                                  args.line_frequency)


    main()
