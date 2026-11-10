"""Tests for the SMU initialisation helper and its connection probe."""
from types import SimpleNamespace

import pytest
import serial
from keithley2600 import KeithleyIOError

import gdnasynth.keithley as keithley

KEITHLEY_IDN = "Keithley Instruments, Model 2602B, 4616013, 1.7.5a"


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
        self.connected = True
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

    def connect(self):
        """Does nothing, for now."""
        return False


class _FakeResource:
    """Stand-in for a pyvisa resource, used to exercise the probe."""

    def __init__(self, identity=None, query_error=None):
        self.identity = identity
        self.query_error = query_error
        self.read_termination = None
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def query(self, command):
        if self.query_error is not None:
            raise self.query_error
        return self.identity

    def close(self):
        self.closed = True


class _FakeResourceManager:
    """Stand-in for pyvisa.ResourceManager."""

    def __init__(self, resource=None, open_error=None):
        self.resource = resource if resource is not None else _FakeResource()
        self.open_error = open_error
        self.opened = []

    def open_resource(self, address):
        self.opened.append(address)
        if self.open_error is not None:
            raise self.open_error
        return self.resource


def _patch_pyvisa(monkeypatch, resource=None, open_error=None):
    """Stub out pyvisa's ResourceManager with a fake one."""
    manager = _FakeResourceManager(resource, open_error)
    monkeypatch.setattr(keithley.pyvisa, "ResourceManager", lambda: manager)
    return manager


def _patch_keithley(monkeypatch, connected=True):
    """Stub out the probe, the driver, and the retry delay."""
    monkeypatch.setattr(keithley, "_probe_keithley", lambda address: None)
    monkeypatch.setattr(keithley.time, "sleep", lambda seconds: None)
    created = {}

    def fake_keithley(visa_address, raise_keithley_errors=False):
        created["smu"] = _FakeKeithley(visa_address, raise_keithley_errors)
        created["smu"].connected = connected
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


def test_initialise_smu_raises_when_the_device_does_not_connect(monkeypatch):
    """Test that a failed connection is reported, not used.

    GIVEN: a Keithley driver that could not connect (``connected`` is False)
    WHEN: initialise_smu(...) is called
    THEN: KeithleyIOError is raised, naming the VISA resource
    """
    _patch_keithley(monkeypatch, connected=False)

    with pytest.raises(KeithleyIOError) as excinfo:
        keithley.initialise_smu("ASRL/dev/ttyUSB0::INSTR", 60, 1.0)

    assert "ASRL/dev/ttyUSB0::INSTR" in str(excinfo.value)


def test_probe_accepts_a_keithley_instrument(monkeypatch):
    """Test that the probe accepts a Keithley and leaves a clean handle.

    GIVEN: a resource that identifies as a Keithley
    WHEN: _probe_keithley(...) is called
    THEN: the address is opened, the read terminator is set, and the resource is
          closed again
    """
    resource = _FakeResource(identity=KEITHLEY_IDN)
    manager = _patch_pyvisa(monkeypatch, resource=resource)

    keithley._probe_keithley("ASRL/dev/ttyUSB0::INSTR")

    assert manager.opened == ["ASRL/dev/ttyUSB0::INSTR"]
    assert resource.read_termination == "\n"
    assert resource.closed is True


def test_probe_rejects_a_non_keithley_instrument(monkeypatch):
    """Test that a wrong device on the port is reported.

    GIVEN: a resource that identifies as something other than a Keithley
    WHEN: _probe_keithley(...) is called
    THEN: KeithleyIOError is raised, naming what was found
    """
    resource = _FakeResource(identity="Acme Pump, Model 3000, 1, 2")
    _patch_pyvisa(monkeypatch, resource=resource)

    with pytest.raises(KeithleyIOError) as excinfo:
        keithley._probe_keithley("ASRL/dev/ttyUSB0::INSTR")

    assert "Acme Pump" in str(excinfo.value)
    assert resource.closed is True


def test_probe_lets_a_visa_error_propagate(monkeypatch):
    """Test that VISA-level failures are not swallowed.

    GIVEN: a resource whose identity query times out
    WHEN: _probe_keithley(...) is called
    THEN: the pyvisa VisaIOError propagates
    """
    import pyvisa

    error = pyvisa.errors.VisaIOError(
        pyvisa.constants.StatusCode.error_timeout)
    resource = _FakeResource(query_error=error)
    _patch_pyvisa(monkeypatch, resource=resource)

    with pytest.raises(pyvisa.errors.VisaIOError):
        keithley._probe_keithley("ASRL/dev/ttyUSB0::INSTR")

    assert resource.closed is True


def test_probe_lets_a_serial_error_propagate(monkeypatch):
    """Test that backend serial failures are not swallowed.

    GIVEN: a resource that cannot be opened (e.g. permission denied)
    WHEN: _probe_keithley(...) is called
    THEN: the pyserial SerialException propagates
    """
    _patch_pyvisa(monkeypatch,
                  open_error=serial.SerialException(13, "Permission denied"))

    with pytest.raises(serial.SerialException):
        keithley._probe_keithley("ASRL/dev/ttyUSB0::INSTR")
