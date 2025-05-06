import logging
from pathlib import Path
from argparse import Namespace, ArgumentParser

from keithley2600 import Keithley2600

from gfet.keithley import connect, select_visa_address
from gfet.generic import (
    float_range,
    range_length,
    write_results,
    build_filename)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


def sweep_operating_points(inst: Keithley2600, args: Namespace):
    """Sweep select operating points."""
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

    _range, _len = range_length(float_range(-1.7, 1.7, 0.01))
    vds_operating_points = (0.01, 0.02, 0.05, 0.07)
    logger.debug("Operating points: %s", vds_operating_points)
    for idx, drain_voltage in enumerate(vds_operating_points, start=1):
        logger.info("Setting drain voltage to %sV", drain_voltage)
        inst.apply_voltage(inst.smub, drain_voltage)
        results = tuple()
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
    def setup_logging(log_level: str):
        logger.setLevel(logging.getLevelNamesMapping()[log_level])

    def main():
        parser = ArgumentParser("Operating Points Selection")
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
                            default="info")
        parser.add_argument("--line-frequency",
                            type=int,
                            choices=(50, 60),
                            default=60)
        args = parser.parse_args()
        setup_logging(args.log_level.upper())

        return sweep_operating_points(
            connect(args.visa_address, retries=args.connection_retries),
            args)


    main()
