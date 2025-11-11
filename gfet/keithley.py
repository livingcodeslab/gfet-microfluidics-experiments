"""Library of common functions to Keithley device(s)."""
import sys
import time
import logging

import pyvisa

from keithley2600 import Keithley2600, KeithleyIOError

logger = logging.getLogger(__name__)

def select_visa_address() -> str:
    resources = pyvisa.ResourceManager().list_resources()
    print("The available VISA addresses are: ")
    for index, address in enumerate(resources):
        print(f"{index} ==> {address}")

    try:
        value = int(input("Enter the number for the chosen address: "))
        return resources[value]
    except ValueError:
        print("Invalid choice! "
              f"Expected a number between 0 and {len(resources) -1} inclusive")
        return ""

def connect(
        visa_address: str,
        retries: int = 10,
        seconds_between_retries: float = 0.5
) -> Keithley2600:
    """Connect to a Keithley2600 device via the LAN cable."""
    # The constructor calls the `connect()` function
    inst = Keithley2600(visa_address, raise_keithley_errors=True)
    retry = 2
    while not inst.connected:
        if retry > retries:
            raise KeithleyIOError(
                f"Failed to connect to Keithley after {retries} attempts.")
            break
        logger.info(f"Connection attempt {retry}")
        if inst.connect():
            return inst
        logger.info("Could not connect to instrument; retrying…")
        time.sleep(seconds_between_retries)
        retry = retry + 1

    return inst


def device_stabilisation(inst: Keithley2600):
    """Stabilise device."""
    logger.info("=== Device stabilisation ===")
    inst.apply_voltage(inst.smua, 0.3)
    inst.apply_voltage(inst.smub, 0.5)
    for _ in range(0, 3):
        inst.measure_voltage(inst.smua)
        inst.measure_current(inst.smua)
        inst.measure_voltage(inst.smub)
        inst.measure_current(inst.smub)
    logger.info("============================")


def initialise_smu(visa_address, line_frequency: int, nplc: float) -> Keithley2600:
    """Initialize the Source-Measure Unit device."""
    smu = Keithley2600(visa_address)

    _int_time_ = __integration_time__(line_frequency, nplc)
    smu.set_integration_time(smu.smua, _int_time_)
    smu.set_integration_time(smu.smub, _int_time_)
    device_stabilisation(smu)
    smu.smua.source.output = smu.smua.OUTPUT_OFF
    smu.smub.source.output = smu.smub.OUTPUT_OFF

    return smu


def __integration_time__(line_frequency: int, nplc: float) -> float:
    """Compute the integration time.

    Arguments:
    line_frequency -- the AC line frequency (50 or 60)
    nplc -- number of power line cycles. Range [0.001, 25]
    """
    if line_frequency not in (50, 60):
        raise ValueError(
            "`line_frequency` must be either 50 or 60.")
    if nplc < 0.001 or nplc > 25:
        raise ValueError(
            "`nplc` must be greater than or equal to 0.001 and less than or "
            "equal to 25.")
    return nplc * (1 / line_frequency)
