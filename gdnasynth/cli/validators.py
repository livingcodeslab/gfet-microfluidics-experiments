"""Command-Line arguments/options validator functions."""
from pathlib import Path
from typing import Union, TypeVar, Callable


def fetch_range_float(value: str) -> tuple[float, float, float]:
    """Convert a string into a tuple of values."""
    _str_items = value.split(",")
    if len(_str_items) not in (2, 3):
        raise ValueError(
            "Invalid range value. Expected two comma-separated values.")

    items = tuple(float(item) for item in _str_items)
    if len(items) == 2:
        items = items + (0.1,)
    if items[0] < items[1]:
        return items # type: ignore[return-value]
    return (items[1], items[0], items[2])


T = TypeVar("T")
def make_value_range_checker(
        low: T, high: T, title: str = "") -> Callable[[str], T]:
    """Return a function that verifies that the value is is given is within the
    range [low, high]."""
    assert type(low) == type(high), (
        "Both `low` and `high` **MUST** be of the same type.")
    def _checker_(val) -> T:
        _val = type(low)(val) # type: ignore[call-arg]
        if low <= _val <= high:# type: ignore[operator]
            return _val
        raise ValueError(
            (f"{title.strip()}: " if bool(title.strip()) else "") +
            f"{_val} is not within [{low}, {high}].")
    return _checker_


def existing_file(argvalue: str) -> Path:
    """Ensure that `argvalue` is an existing file."""
    _file = Path(argvalue)
    assert _file.exists() and _file.is_file(), (
        "The path provided *MUST* exist and be a file.")
    return _file


def existing_directory(argvalue: Union[str, Path]) -> Path:
    """Ensure that `argvalue` is an existing directory."""
    _file = Path(argvalue)
    assert _file.exists() and _file.is_dir(), (
        "The path provided *MUST* exist and be a directory.")
    return _file
