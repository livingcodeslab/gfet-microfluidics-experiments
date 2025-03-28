#!/usr/bin/env python3
#coding=utf-8
import logging
from pathlib import Path
from argparse import Namespace, ArgumentParser

from pygnuplot import gnuplot

from gfet.cli import fetch_range_float
from gfet.generic import float_range, range_length, build_filename

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)
#logger.addHandler(logging.StreamHandler())


def plot_files(args: Namespace):
    g = gnuplot.Gnuplot(log=True)

    _ylabel = "R (KΩ)" if args.y_axis == "drain_resistance" else "I_D (A)"

    # Set plotting style
    g.set(terminal='svg font "arial,10" fontscale 1.0 size 1200,1000 dynamic background rgb "white"',
          #terminal='pngcairo font "arial,10" fontscale 1.0 size 1000, 800',
          # output='"testplot.1.png"',
          output=f'"{args.plot_filename}"',
          key="fixed left top horizontal Right noreverse enhanced autotitle box lt black linewidth 1.000 dashtype solid",
          # samples="50, 50",
          title=f'"{args.plot_title}" font ",20" textcolor lt -1 norotate',
          datafile='separator ","',
          # xtics=0.005,
          xrange='[* : *] noreverse writeback',
          # x2range='[* : *] noreverse writeback',
          yrange='[* : *] noreverse writeback',
          # y2range='[* : *] noreverse writeback',
          zrange='[* : *] noreverse writeback',
          cbrange='[* : *] noreverse writeback',
          rrange='[* : *] noreverse writeback',
          colorbox='vertical origin screen 0.9, 0.2 size screen 0.05, 0.6 front noinvert bdefault',
          xlabel='"V_G (V)"',
          ylabel=f'"{_ylabel}" rotate')

    g.cmd("NO_ANIMATION = 1")

    _range, _len = range_length(float_range(*args.range))
    plot_args = [
        (f"'{build_filename(args.input_directory, args.file_prefix, idx, _len)}' "
         f"using 'x_axis':'{args.y_axis}' "
         f"title 'Gate Voltage {gate_voltage:0.3}V' "
         "with lines")
        for idx, gate_voltage in enumerate(_range, start=1)]

    g.plot(*plot_args)


def main():
    """Entry-point function."""
    parser = ArgumentParser("GFET Characteristics")
    parser.add_argument("--plot-filename", type=Path,
                        default="./gfet_characteristics_plot.svg")
    parser.add_argument(
        "--input-directory",
        type=Path,
        default=Path("./GFET_Characteristics_results").absolute(),
        help="Directory with the files to plot.")
    parser.add_argument(
        "--file-prefix", type=str, default="result",
        help="File prefix used to generate the files during measurement.")
    parser.add_argument(
        "--range", type=fetch_range_float, default=(-1.7, 1.7, 0.1),
        help=("A comma-separated list of 2 or 3 float values. "
              "If 3 values are provided, the third is used as a step. "
              "If only 2 values are provided, the default step is 0.1"))
    parser.add_argument(
        "--plot-title", type=str, default="GFET Characteristics",
        help="Title of the plot.")
    parser.add_argument("--x-axis", type=str, default="gate_voltage")
    parser.add_argument("--y-axis", type=str, default="drain_current")
    parser.add_argument(
        "--log-level", type=str, default="info",
        choices=("critical", "error", "warning", "info", "debug"))
    args = parser.parse_args()
    logger.setLevel(args.log_level.upper())
    logger.debug("CLI arguments: %s", args)
    plot_files(args)
    return 0

if __name__ == "__main__":
    main()
