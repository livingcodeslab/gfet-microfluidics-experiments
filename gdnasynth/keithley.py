"""Library of common functions to Keithley device(s)."""
import sys
import time
import logging
from typing import cast

import pyvisa
from pyvisa.resources import MessageBasedResource

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

def _probe_keithley(visa_address: str) -> None:
    """Probe Keithley device directly to surface permission errors/busy device.

    The keithley2600 driver hides the reason why a connection fails. This forces
    an exception to be raised in case the user does not have appropriate
    permissions or the device is busy.

    :param visa_address: The VISA address to the device you wish to connect to
    :type visa_address: str

    :raises keithley2600.KeithleyIOError when connection is made to non-keithley
            device
    :raises serial.SerialException propagated from pyvisa
    :raises pyvisa.VisaIOError propagated from pyvisa
    """
    with cast(MessageBasedResource,
              pyvisa.ResourceManager().open_resource(visa_address)) as rsc:
        rsc.read_termination = "\n"
        identity = rsc.query("*IDN?").strip()
        logger.info("Found: %s", identity)
        if not identity.startswith("Keithley Instruments,"):
            raise KeithleyIOError(f"Not a Keithley instrument: '{identity}'!")


def connect(
        visa_address: str,
        retries: int = 10,
        seconds_between_retries: float = 0.5,
        raise_keithley_errors: bool = False
) -> Keithley2600:
    """Connect to a Keithley2600 device via the LAN cable."""
    _probe_keithley(visa_address)
    inst = Keithley2600(visa_address,
                        raise_keithley_errors=raise_keithley_errors)
    if inst.connected:
        return inst

    for retry in range(1, retries+1):
        logger.warning(f"Reconnection attempt {retry}/{retries}")
        if inst.connect():
            return inst
        time.sleep(seconds_between_retries)

    raise KeithleyIOError(
        "Could not connect to the Source-Measure Unit at "
        f"{visa_address} even with {retries} attempts. "
        "Check the VISA resource (pyvisa.ResourceManager()"
        ".list_resources()), the device permissions, and that the "
        "instrument is powered on.")


def initialise_smu(
        visa_address: str,
        line_frequency: int,
        nplc: float,
        raise_keithley_errors: bool = False
) -> Keithley2600:
    """Initialize the Source-Measure Unit device."""
    smu = connect(visa_address, raise_keithley_errors=raise_keithley_errors)
    logger.info("Keithley 2602B SMU Serial Number: %s", smu.localnode.serialno)

    _int_time_ = __integration_time__(line_frequency, nplc)
    smu.set_integration_time(smu.smua, _int_time_)
    smu.set_integration_time(smu.smub, _int_time_)
    smu.smua.source.func = smu.smua.OUTPUT_DCVOLTS
    smu.smub.source.func = smu.smub.OUTPUT_DCVOLTS
    smu.smua.source.limiti = 0.1
    smu.smub.source.limiti = 0.1
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
