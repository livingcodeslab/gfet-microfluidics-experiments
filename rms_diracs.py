"""Compute RMS values for dirac points"""
import sys
import csv
import math
from pathlib import Path
from typing import Union, Iterator
from argparse import ArgumentParser

def compute_window(idx: int, length: int, window_size: int) -> tuple[int, int, int]:
    """Compute the indices that give the appropriate window for a given index."""
    lo = idx - math.floor(window_size/2)
    hi = idx + math.ceil(window_size/2)
    if lo < 0:
        return (0, hi-lo, idx)
    if hi > length:
        return (lo-(hi-length), length, idx)
    return (lo, hi, idx)

def read_file(path: Path) -> Iterator[dict[str, float]]:
    """Return a generator for the lines in the given file."""
    with path.open(mode="r", encoding="utf8") as _file:
        reader = csv.DictReader(_file)
        for row in reader:
            yield {key: float(val) for key,val in row.items()}


def sqr(val: Union[int, float, complex]) -> Union[int, float, complex]:
    """Compute the square of a number."""
    return val*val


def compute_rms_gate_voltages(diracs_file: Path, window_size):
    diracs = tuple(read_file(diracs_file))
    length = len(diracs)
    windows = (
        compute_window(idx, length, window_size) for idx in range(0, length))
    writer = csv.DictWriter(sys.stdout, fieldnames=tuple(diracs[0].keys()) + ("rms_gate_voltage",))
    writer.writeheader()
    for window in windows:
        lo, hi, idx = window
        rms = math.sqrt(
            sum(pow(row["measured_gate_voltage"], 2) for row in diracs[lo:hi])
            / len(window))
        writer.writerow({**diracs[idx], "rms_gate_voltage": rms})


if __name__ == "__main__":
    def main():
        """Entry to rms-diracs."""
        parser = ArgumentParser(
            "rms-diracs",
            description="Compute the RMS values for dirac points in given file.")
        parser.add_argument(
            "raw_diracs_file",
            metavar="raw-diracs-file",
            type=Path)
        parser.add_argument(
            "--window_size",
            "--window-size",
            metavar="window-size",
            type=int,
            default=5)
        args = parser.parse_args()
        return compute_rms_gate_voltages(args.raw_diracs_file, args.window_size)

    sys.exit(main())
