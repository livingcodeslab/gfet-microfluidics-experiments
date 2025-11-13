"""Script to run specific fluid patterns."""
import time
import serial
import logging
import argparse

from gdnasynth.logging import set_loggers_level
from read_smu_continuously import print_line
from microfluidics import (collect,
                           Channel,
                           REAGENT_CHANNELS,
                           vent_chip2collection)

logger = logging.getLogger(__name__)
logging.basicConfig(
    encoding="utf-8",
    format="%(asctime)s - %(name)s - %(levelname)s — %(message)s")


def run_fluid_detection_loop(mfd_port: serial.Serial) -> int:
    """Run the fluid detection loop."""
    logger.info("=== Fluid detection loop ===")
    print_line(("t","event"))
    for chan in REAGENT_CHANNELS[0:3]:
        logger.info("Collecting plugs for reagent %s", chan.value)

        print_line((time.time(), "Vent to Collection."))
        vent_chip2collection(mfd_port, seconds=120)
        print_line((time.time(), "End: Vent to Collection."))

        for idx in range(0, 5):
            print_line((time.time(),
                        f"Collect 5 seconds from {chan.value} (rep: {idx})"))
            collect(mfd_port, chan, seconds=5)

            print_line((
                time.time(),
                (f"Vent to collection for 1 second "
                 f"(channel: {chan.value} rep: {idx})")))
            vent_chip2collection(mfd_port, seconds=1)

        logger.info("Push solid reagent %s flow out to waste", chan.value)

        print_line((time.time(),
                    f"Collect 90 seconds (channel: {chan.value})"))
        collect(mfd_port, chan, seconds=90)

        print_line((time.time(),
                    "Vent 120 seconds to collection"))
        logger.info("Venting the GFET line completely")
        vent_chip2collection(mfd_port, seconds=120)# vent to collection/waste
        print_line((time.time(),
                    f"End run (channel: {chan.value})"))

    return 0


def run_fluid_pattern(mfd_port: serial.Serial, chan: Channel) -> int:
    """Run the fluid detection loop."""
    logger.info("=== Fluid pattern ===")
    print_line(("t","event"))
    logger.info("Collecting plugs for reagent %s", chan.value)

    print_line((time.time(), "Vent to Collection."))
    vent_chip2collection(mfd_port, seconds=120)
    print_line((time.time(), "End: Vent to Collection."))

    for idx in range(0, 5):
        print_line((time.time(),
                    f"Collect 5 seconds from {chan.value} (rep: {idx})"))
        collect(mfd_port, chan, seconds=5)

        print_line((
            time.time(),
            (f"Vent to collection for 1 second "
             f"(channel: {chan.value} rep: {idx})")))
        vent_chip2collection(mfd_port, seconds=1)

    logger.info("Push solid reagent %s flow out to waste", chan.value)

    print_line((time.time(),
                f"Collect 90 seconds from {chan.value}"))
    collect(mfd_port, chan, seconds=90)

    print_line((time.time(),
                "Vent 120 seconds to collection"))
    logger.info("Venting the GFET line completely")
    vent_chip2collection(mfd_port, seconds=120)# vent to collection/waste
    print_line((time.time(),
                f"End run for {chan.value}"))

    return 0


def main():
    """`run_fluid_detection_loop`: entry point."""
    parser = argparse.ArgumentParser("run_fluid_pattern")
    parser.add_argument(
        "reagent_channel",
        metavar="reagent-channel",
        type=int,
        choices=(1, 2, 3, 4, 5, 6, 7, 8),
        help="The channel to run the fluid pattern on.")
    parser.add_argument(
        "--microfluidics-serial-port",
        type=str,
        default="/dev/ttyACM0",
        help=(
            "The serial port path to the system device that grants access "
            "to the microfluidics device. Default (/dev/ttyACM0)"))
    parser.add_argument(
        "--log-level",
        type=str,
        choices=("critical",
                 "error",
                 "warning",
                 "info",
                 "debug"),
        default="info")

    args = parser.parse_args()
    logger.setLevel(getattr(logging, args.log_level.upper()))
    set_loggers_level(("microfluidics", "gfet.keithley"),
                      logger.getEffectiveLevel())

    return run_fluid_pattern(
        serial.Serial(args.microfluidics_serial_port),
        REAGENT_CHANNELS[args.reagent_channel - 1])


if __name__ == "__main__":
    main()
