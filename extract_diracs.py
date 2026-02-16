"""Extract lines with the Dirac points from the raw data."""
import csv
import sys
import logging
from pathlib import Path
from typing import Iterator
from argparse import ArgumentParser

from gdnasynth.logging import setup_logging
from gdnasynth.cli.options import cli_add_logging_arg

logger = logging.getLogger("extract-diracs")

ParsedLine = tuple[float, float, float, float, float, float, float]


def raw_file_data(rawfile: Path) -> Iterator[str]:
    """Open the file and return the lines, one at a time."""
    with rawfile.open(mode="r", encoding="utf8") as rawfile:
        for line in rawfile:
            yield line


def parse_line(line: str) -> ParsedLine:
    """Clean up the lines from the raw file."""
    return tuple(
        float(field.strip().strip('"')) for field in line.strip().split(","))


def group_sweeps(records: Iterator[dict[str, float]]) -> Iterator[
        tuple[dict[str, float], ...]]:
    """Group the data into separate sweeps"""
    chunksize = 100 # 1.0/0.01
    _chunk = tuple()
    try:
        while True:
            for i in range(0, chunksize):
                _chunk = _chunk + (next(records),)

            yield _chunk
            _chunk = tuple()
    except StopIteration:
        pass


def extract_diracs(rawfile: Path):
    """Extract lines with the dirac points/voltages from the raw data."""
    rawdata = raw_file_data(rawfile)
    headers = tuple(
        field.strip('"') for field in next(rawdata).strip().split(","))

    diracs = (
        min(sweep, key=lambda swp: swp["drain_current"])
        for sweep in
        group_sweeps(
            record
            for record in
            ((dict(zip(headers, parse_line(line))) for line in rawdata))
            if record["provided_gate_voltage"] > 0))
    writer = csv.DictWriter(sys.stdout, fieldnames=headers)
    writer.writeheader()
    writer.writerows(diracs)
        

if __name__ == "__main__":

    def main():
        parser = cli_add_logging_arg(ArgumentParser(
            "extract-diracs",
            description="Extract lines with the dirac voltages from the raw data"))
        parser.add_argument(
            "raw_data_file",
            metavar="RAW-DATA-FILE",
            type=Path,
            help="Path to the data file with only the raw data for positive channel voltages.")
        args = parser.parse_args()
        setup_logging(args.log_level, logger)
        return extract_diracs(args.raw_data_file)

    sys.exit(main())
