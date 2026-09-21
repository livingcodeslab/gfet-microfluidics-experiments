"""Build the configuration file."""
import sys
import json
from pathlib import Path
from dataclasses import asdict
from urllib.parse import urljoin

import requests

from .types import (LabwareConfig,
                    PipetteConfig,
                    Configuration,
                    OpentronsVersion,
                    ConfigurationException)


_OPENTRONS_VERSIONS = [1, 2, 3]


def fetch_opentrons_version() -> OpentronsVersion:
    """Fetch the Opentrons version to be used."""
    _ver = input(
        "Enter the Opentrons version you wish to use [1, 2, 3]: ").strip()
    if _ver == "*":
        return "*"

    try:
        ver = int(_ver, base=10)
        if ver not in _OPENTRONS_VERSIONS:
            raise ValueError("Not in versions.")
        return ver # type: ignore [return-value]
    except ValueError as _verr:
        raise ConfigurationException(
            "Valid Opentrons version values are *, "
            f"{', '.join(str(i) for i in _OPENTRONS_VERSIONS)}"
        ) from _verr


def fetch_custom_labware_definition_paths() -> tuple[Path, ...]:
    """Fetch paths to custom labware definition paths."""
    return tuple()


def fetch_robot_url() -> str:
    """Fetch the URL to the robot's HTTP API from the user."""
    addr: str = input("Please enter the URL/IP Address to the robot: ")
    testp: str = input(
        "Do you want to test access to the robot? [yes/no]: ").lower()
    match testp:
        case "yes":
            result = requests.get(urljoin(addr, "/redoc"), timeout=(9.13, 20))
            if result.status_code == "200":
                print("URL verified!")
                return addr
            raise ConfigurationException("ERROR: Could not verify the URL")
        case "no":
            print(
                "WARNING: URL not verified. This configuration might not work.",
                file=sys.stderr)
            return addr
        case _:
            raise ConfigurationException(
                "Could not understand response. Quiting!")


def fetch_labware_slots() -> tuple[LabwareConfig, ...]:
    """Fetch the labware used and the slots for each."""
    return tuple()


def fetch_pipettes() -> tuple[PipetteConfig, ...]:
    """Fetch the pipette(s) to be used and the mount(s) for each."""
    return tuple()


def main():
    """Entry point to the program."""
    ot_version = fetch_opentrons_version()
    defns = fetch_custom_labware_definition_paths()
    config = Configuration(
        fetch_robot_url(),
        fetch_labware_slots(),
        fetch_pipettes(),
        opentrons_version=ot_version,
        custom_labware_definitions=defns)
    print(json.dumps(asdict(config), indent=4))
    return 0

sys.exit(main())
