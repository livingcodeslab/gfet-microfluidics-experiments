"""Microfluidics device functions"""
import time
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class Channel(Enum):
    """Channel Descriptor"""
    WSHL = 0 # Wash line, also used as "NULL" channel
    CH01 = 1
    CH02 = 2
    CH03 = 3
    CH04 = 4
    CH05 = 5
    CH06 = 6
    CH07 = 7
    CH08 = 8
    VENT = 9

REAGENT_CHANNELS = tuple(
    chan for chan in Channel
    if chan not in
    (Channel.WSHL, Channel.VENT))


class CommandError(Exception):
    "Exception to raise in case of a command failure."
    

def send_and_wait_for_response(port, cmd: str, line_num: int = -1) -> bool:
    """Send a command and wait for the response."""
    cmd = cmd.encode()
    logger.debug("Sending command\n\t%s\nto port \n\t%s.\n", cmd, port)
    port.write(cmd)

    while True:
        response = port.readline().decode().strip()
        if response == "ERR":
            raise Exception(
                f"{line_num} | {response} | Error executing command ('{cmd}')")
        if response == "FIN":
            logger.debug(f"{line_num} | Command executed successfully.")
            break

        # Empty response
        time.sleep(0.5)

    return True


def compile_command(
        command: str,
        subcommand: str,
        channel: Channel,
        seconds: int = 25,
        rpm: int = 36
) -> str:
    """Build the command from the various parts."""
    return f"{command} {subcommand} {channel.value} -T {seconds} -R {rpm}\n"


def prime(
        port, command: str, channel: Channel, seconds: int = 25, rpm: int = 36
) -> bool:
    """Prime wash/reagent."""
    assert command in ("CHEM_WASH", "-C")
    return send_and_wait_for_response(
        port,
        compile_command("PRIME", command, channel, seconds, rpm))

def prime_wash_to_channel(
        port, channel: Channel, seconds: int = 25, rpm: int = 36) -> bool:
    """Prime the wash reagent to a specific channel."""
    _allowed = REAGENT_CHANNELS + (Channel.WSHL,)
    assert channel in _allowed, "Invalid channel!"
    return prime(port, "CHEM_WASH", channel, seconds, rpm)

def prime_reagent_to_channel(
        port, channel: Channel, seconds: int = 25, rpm: int = 36) -> bool:
    """Prime the reagent for a specific channel."""
    assert channel in REAGENT_CHANNELS, "Invalid channel!"
    return prime(port, "CHEM_WASH", channel, seconds, rpm)


def wash(
        port, command: str, channel: Channel, seconds: int = 25, rpm: int = 36
) -> bool:
    """Run wash reagent on the specified channel."""
    assert command in ("-C", "COLLECTION", "COMMON")
    return send_and_wait_for_response(
        port,
        compile_command("WASH", command, channel, seconds, rpm))


def wash_common(port, seconds: int = 25, rpm: int = 36) -> bool:
    """Wash common line up to before the chip, out to waste."""
    return wash(port, "COMMON", Channel.WSHL, seconds, rpm)


def wash_chip(port, seconds: int = 25, rpm: int = 36) -> bool:
    """Wash common line up to before the chip, out to waste."""
    return wash(port, "COLLECTION", Channel.WSHL, seconds, rpm)


def vent(port, command: str, seconds: int = 25, rpm: int = 36) -> bool:
    """Run wash reagent on the specified channel."""
    assert command in ("ALL", "COMMON")
    return send_and_wait_for_response(
        port,
        compile_command("PURGE", command, Channel.WSHL, seconds, rpm))


def vent_common(port, seconds: int = 25, rpm: int = 36) -> bool:
    """Vent atmosphere through the common line out to waste."""
    return vent(port, "COMMON", seconds, rpm)


def vent_chip2waste(port, seconds: int = 25, rpm: int = 36) -> bool:
    """Vent atmosphere through common line, chip and out to waste"""
    return vent(port, "ALL", seconds, rpm)


def collect(port, channel: Channel, seconds: int = 25, rpm: int = 36) -> bool:
    """Collect reagent or vent atmosphere out to collection"""
    assert channel in (REAGENT_CHANNELS + (Channel.VENT,)), (
        f"Invalid channel: {channel}")
    return send_and_wait_for_response(
        port,
        compile_command("COLLECT", "-C", channel, seconds, rpm))


def vent_chip2collection(port, seconds: int = 25, rpm: int = 36) -> bool:
    """Vent atmosphere through common line, chip and out to collection."""
    return collect(port, Channel.VENT, seconds, rpm)
