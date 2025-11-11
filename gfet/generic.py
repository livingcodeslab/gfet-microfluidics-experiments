"""Generic utilities"""
import csv
import logging
from pathlib import Path
from typing import Union, Iterator

logger = logging.getLogger(__name__)


def float_range(
        low: Union[int, float],
        high: Union[int, float],
        step: Union[int, float] = 1
) -> Iterator[float]:
    """Same a `range` but allows floating-point values."""
    current = float(low)
    while current < high:
        yield current
        current = current + step


def float_range2(high: int, steps: int, low: int = 0) -> Iterator[float]:
    """Return `steps` equally-spaced values from `low` to `high`."""
    _diff = (high-low)
    for val in range(low, steps*_diff, _diff):
        yield val/steps


def build_filename(
        outdir: Path, file_prefix: str, index: int, total_files: int) -> Path:
    if not outdir.exists():
        outdir.mkdir()

    padding = len(str(total_files))
    if padding < 2:
        padding = 2

    return outdir.joinpath(f"{file_prefix}_{index:0{padding}}.csv")


def range_length(the_range: Iterator[float]) -> tuple[tuple[float, ...], int]:
    """Compute the range and its length"""
    _range = tuple(the_range)
    return (_range, len(_range))


def write_results(filepath: Path, results: tuple[dict, ...]):
    # TODO: remove these debug statements
    logger.debug("Fieldnames: %s", list(results[0].keys()))
    # END: TODO: remove these debug statements
    with filepath.open("w") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
