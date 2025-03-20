#!/usr/bin/env python3
#coding=utf-8
from pygnuplot import gnuplot

from gfet.generic import float_range

g = gnuplot.Gnuplot(log=True)

# Set plotting style
g.set(terminal='svg font "arial,10" fontscale 1.0 size 1200,1000 dynamic background rgb "white"',
      #terminal='pngcairo font "arial,10" fontscale 1.0 size 1000, 800',
      # output='"testplot.1.png"',
      output='"testplot.1.svg"',
      key="fixed left top horizontal Right noreverse enhanced autotitle box lt black linewidth 1.000 dashtype solid",
      # samples="50, 50",
      title='"GFET Characteristics" font ",20" textcolor lt -1 norotate',
      datafile='separator ","',
      # xtics=0.005,
      xrange='[* : *] noreverse writeback',
      # x2range='[* : *] noreverse writeback',
      yrange='[* : *] noreverse writeback',
      # y2range='[* : *] noreverse writeback',
      zrange='[* : *] noreverse writeback',
      cbrange='[* : *] noreverse writeback',
      rrange='[* : *] noreverse writeback',
      colorbox='vertical origin screen 0.9, 0.2 size screen 0.05, 0.6 front noinvert bdefault')

g.cmd("NO_ANIMATION = 1")

plot_args = [
    (f"'GFET_Characteristics_results/result_{idx:05}.csv' "
     f"using 'x_axis':'drain_current' title 'Gate Voltage {gate_voltage:0.2}V' "
     "with linespoint")
    for idx, gate_voltage in enumerate(float_range(-1, 1, 0.1), start=1)]

g.plot(*plot_args)
