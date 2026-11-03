"""Tests for the SMU initialisation helper."""
from types import SimpleNamespace

import gdnasynth.keithley as keithley


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


class _FakeKeithley:
    """A minimal stand-in for a Keithley2600."""

    def __init__(self, visa_address, raise_keithley_errors=False):
        self.visa_address = visa_address
        self.raise_keithley_errors = raise_keithley_errors
        self.smua = _Channel("a")
        self.smub = _Channel("b")
        self.localnode = SimpleNamespace(serialno="4616013")
        self.calls = []
        self.integration_times = {}

    def set_integration_time(self, channel, value):
        self.calls.append(("set_integration_time", channel.name, value))
        self.integration_times[channel.name] = value

    def apply_voltage(self, channel, value):
        self.calls.append(("apply_voltage", channel.name, value))

    def measure_voltage(self, channel):
        self.calls.append(("measure_voltage", channel.name))
        return 0.0

    def measure_current(self, channel):
        self.calls.append(("measure_current", channel.name))
        return 0.0


def _patch_keithley(monkeypatch):
    created = {}

    def fake_keithley(visa_address, raise_keithley_errors=False):
        created["smu"] = _FakeKeithley(visa_address, raise_keithley_errors)
        return created["smu"]

    monkeypatch.setattr(keithley, "Keithley2600", fake_keithley)
    return created


def test_initialise_smu_sets_up_both_channels(monkeypatch):
    """Test that initialise_smu configures the channels and switches off.

    GIVEN: the Keithley constructor is stubbed out
    WHEN: initialise_smu(...) is called
    THEN: integration time, source function and compliance are set, and the
          outputs are left off
    """
    created = _patch_keithley(monkeypatch)

    smu = keithley.initialise_smu("visa", 60, 1.0)

    assert smu is created["smu"]
    assert smu.integration_times == {"a": 1.0 / 60, "b": 1.0 / 60}
    assert smu.smua.source.func == "dcvolts"
    assert smu.smub.source.func == "dcvolts"
    assert smu.smua.source.limiti == 0.1
    assert smu.smub.source.limiti == 0.1
    assert smu.smua.source.output == "off"
    assert smu.smub.source.output == "off"


def test_initialise_smu_does_not_condition_the_chip(monkeypatch):
    """Test that initialising the SMU leaves chip conditioning to the caller.

    GIVEN: the Keithley constructor is stubbed out
    WHEN: initialise_smu(...) is called
    THEN: no voltages are applied and no measurements are taken
    """
    created = _patch_keithley(monkeypatch)

    keithley.initialise_smu("visa", 60, 1.0)

    kinds = {call[0] for call in created["smu"].calls}
    assert kinds == {"set_integration_time"}
