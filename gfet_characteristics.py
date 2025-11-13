"""GFET Characteristics code."""
import csv
import logging
from pathlib import Path
from argparse import Namespace, ArgumentParser

from keithley2600 import Keithley2600

from gdnasynth.cli import fetch_range_float
from gdnasynth.keithley import connect, select_visa_address
from gdnasynth.generic import (
    float_range,
    range_length,
    write_results,
    build_filename)

from gdnasynth.logging import set_loggers_level

_module_name_ = __name__
logger = logging.getLogger(__name__)
logHandler = logging.StreamHandler()
logHandler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s — %(message)s"))
logger.addHandler(logHandler)
logger.setLevel(logging.WARNING)


def perform_experiment(
        inst: Keithley2600,
        args: Namespace
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
    integration_time = (0.001 + (1 / args.line_frequency)) / 2 # halfway between
    inst.set_integration_time(inst.smua, integration_time)
    inst.set_integration_time(inst.smub, integration_time)

    ### Device stabilization for liquid gating
    logger.info("Device stabilisation started…")
    inst.apply_voltage(inst.smua, 0.3)
    inst.apply_voltage(inst.smub, 0.5)
    for _ in range(0, 3):
        inst.measure_voltage(inst.smua)
        inst.measure_current(inst.smua)
        inst.measure_voltage(inst.smub)
        inst.measure_current(inst.smub)
    logger.info("Device stabilisation completed.")
    ### END: Device stabilization for liquid gating

    _range, _len = range_length(float_range(*args.range))
    for idx, drain_voltage in enumerate(_range, start=1):
        inst.apply_voltage(inst.smub, drain_voltage)
        results = tuple()
        # for drain_voltage in float_range(-1, 1, 0.00005):
        for gate_voltage in _range:
            inst.apply_voltage(inst.smua, gate_voltage)
            measured_drain_voltage = inst.measure_voltage(inst.smub)
            measured_drain_current = inst.measure_current(inst.smub)
            if measured_drain_current == 0.0:
                drain_resistance = ""
            else:
                drain_resistance = (
                    (measured_drain_voltage/measured_drain_current) / 1000)
            results = results + ({
                "x_axis": f"{gate_voltage:0.3}",
                "gate_voltage": inst.measure_voltage(inst.smua),
                "gate_current": inst.measure_current(inst.smua),
                "drain_voltage": measured_drain_voltage,
                "drain_current": measured_drain_current,
                "drain_resistance": drain_resistance
            },)

        write_results(
            build_filename(args.output_directory, args.file_prefix, idx, _len),
            results)

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
        parser.add_argument(
            "--range", type=fetch_range_float, default=(-1.7, 1.7, 0.1),
            help=("A comma-separated list of 2 or 3 float values. "
                  "If 3 values are provided, the third is used as a step. "
                  "If only 2 values are provided, the default step is 0.1"))
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
                            default="info")
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
        logger.info("Running with a range from %sV to %sV with a step of %s",
                    *args.range)
        return perform_experiment(connect(args.visa_address,
                                          retries=args.connection_retries),
                                  args)


    main()
