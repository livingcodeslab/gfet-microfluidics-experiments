"""Code to integrate with the Opentrons OT-2R robot."""
from importlib import resources
from pathlib import Path


def labware_definition_path(filename: str) -> Path:
    """Path to a labware definition bundled with the package.

    :param filename: The definition's file name, e.g.
        ``"OT2_labware_definition_graphenea_card.json"``.
    :type filename: str

    :rtype pathlib.Path
    """
    files = resources.files(__name__).joinpath("labware")
    return Path(str(files.joinpath(filename)))
