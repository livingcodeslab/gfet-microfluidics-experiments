"""Tests for the chip (Graphenea GFET) conditioning helpers."""
from types import SimpleNamespace

import pytest

from gdnasynth.graphenea import stabilise_chip


class _Source:
    """Stand-in for a Keithley source configuration."""

    def __init__(self):
        self.func = None
        self.limiti = None
        self.output = None


class _Channel:
    """Stand-in for one Keithley channel."""

    OUTPUT_DCVOLTS = "dcvolts"
    OUTPUT_OFF = "off"

    def __init__(self, name):
        self.name = name
        self.source = _Source()


class _FakeSmu:
    """A minimal stand-in for a Keithley2600, recording the calls made."""

    def __init__(self):
        self.smua = _Channel("a")
        self.smub = _Channel("b")
        self.localnode = SimpleNamespace(serialno="4616013")
        self.calls = []

    def apply_voltage(self, channel, value):
        self.calls.append(("apply_voltage", channel.name, value))

    def measure_voltage(self, channel):
        self.calls.append(("measure_voltage", channel.name))
        return 0.0

    def measure_current(self, channel):
        self.calls.append(("measure_current", channel.name))
        return 0.0


def test_stabilise_chip_applies_the_chip_voltages():
    """Test that the chip is biased at its conditioning voltages.

    GIVEN: a fake SMU
    WHEN: stabilise_chip(...) is called
    THEN: 0.3 V is applied to channel A and 0.05 V to channel B
    """
    smu = _FakeSmu()

    stabilise_chip(smu)

    assert ("apply_voltage", "a", 0.3) in smu.calls
    assert ("apply_voltage", "b", 0.05) in smu.calls


def test_stabilise_chip_takes_three_readings_per_channel():
    """Test that both channels are read repeatedly to settle the chip.

    GIVEN: a fake SMU
    WHEN: stabilise_chip(...) is called
    THEN: each channel's voltage and current are measured three times
    """
    smu = _FakeSmu()

    stabilise_chip(smu)

    assert smu.calls.count(("measure_voltage", "a")) == 3
    assert smu.calls.count(("measure_current", "a")) == 3
    assert smu.calls.count(("measure_voltage", "b")) == 3
    assert smu.calls.count(("measure_current", "b")) == 3


@pytest.mark.parametrize("gate,channel,readings",
                         [(0.1, 0.2, 1), (1.0, -1.0, 5)])
def test_stabilise_chip_honours_its_parameters(gate, channel, readings):
    """Test that the conditioning is parameterisable.

    GIVEN: non-default gate/channel voltages and a reading count
    WHEN: stabilise_chip(...) is called
    THEN: those values are used instead of the defaults
    """
    smu = _FakeSmu()

    stabilise_chip(smu, gate_voltage=gate, channel_voltage=channel,
                   readings=readings)

    assert ("apply_voltage", "a", gate) in smu.calls
    assert ("apply_voltage", "b", channel) in smu.calls
    assert smu.calls.count(("measure_voltage", "a")) == readings
    assert smu.calls.count(("measure_current", "b")) == readings
