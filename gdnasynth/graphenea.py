"""Chip (Graphenea GFET) conditioning.

These helpers drive a chip through the SMU, but they are about the **chip**, not
the instrument: `gdnasynth.keithley.initialise_smu(...)` only prepares the SMU.
Call `stabilise_chip(...)` once for each chip being worked with, after the SMU is
initialised and the measurement path is connected to that chip.
"""
import logging

from keithley2600 import Keithley2600

logger = logging.getLogger(__name__)


def stabilise_chip(
        smu: Keithley2600,
        gate_voltage: float = 0.3,
        channel_voltage: float = 0.05,
        readings: int = 3
) -> None:
    """Condition a chip by biasing it and reading it back.

    Applies the gate and channel voltages, then takes `readings` rounds of
    voltage/current measurements on both channels.

    :param smu: The initialised SMU.
    :type smu: keithley2600.Keithley2600
    :param gate_voltage: The gate bias to condition at, in volts.
    :type gate_voltage: float
    :param channel_voltage: The channel bias to condition at, in volts.
    :type channel_voltage: float
    :param readings: How many rounds of measurements to take.
    :type readings: int

    :rtype None
    """
    logger.info("=== Chip stabilisation ===")
    smu.apply_voltage(smu.smua, gate_voltage)
    smu.apply_voltage(smu.smub, channel_voltage)
    for _ in range(readings):
        smu.measure_voltage(smu.smua)
        smu.measure_current(smu.smua)
        smu.measure_voltage(smu.smub)
        smu.measure_current(smu.smub)
    logger.info("=========================")
