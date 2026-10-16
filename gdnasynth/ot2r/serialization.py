"""Transform our objects into JSON-ready primitives."""
import dataclasses
import datetime
import uuid
from collections.abc import Mapping
from enum import Enum
from functools import singledispatch
from typing import Any

from gdnasynth.ot2r.commands.base_types import NonEmptyString


@singledispatch
def to_jsonable(obj: Any) -> Any:
    """Recursively convert ``obj`` into JSON-ready primitives.

    Dataclasses become dicts, enums become their values, ``datetime``
    becomes an ISO-8601 string, ``uuid.UUID`` and ``NonEmptyString``
    become strings, and mappings/sequences become dicts/lists.  Plain JSON
    primitives pass through unchanged.

    This is a ``singledispatch`` function: a type can supply its own
    conversion via ``to_jsonable.register(...)``, which takes precedence
    over the default dataclass handling.

    :param obj: The object to convert.
    :type obj: Any

    :rtype: dict | list | str | int | float | bool | None

    :raises TypeError: if ``obj`` is of an unsupported type.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name))
                for f in dataclasses.fields(obj)}
    raise TypeError(
        f"Cannot serialise object of type {type(obj).__name__!r}")


@to_jsonable.register(type(None))
@to_jsonable.register(bool)
@to_jsonable.register(int)
@to_jsonable.register(float)
@to_jsonable.register(str)
def _primitive(obj: Any) -> Any:
    """Primitives pass through unchanged."""
    return obj


@to_jsonable.register(Enum)
def _enum(obj: Enum) -> Any:
    """Enum members become their values."""
    return to_jsonable(obj.value)


@to_jsonable.register(datetime.datetime)
def _datetime(obj: datetime.datetime) -> str:
    """``datetime`` becomes an ISO-8601 string."""
    return obj.isoformat()


@to_jsonable.register(uuid.UUID)
def _uuid(obj: uuid.UUID) -> str:
    """``uuid.UUID`` becomes a string."""
    return str(obj)


@to_jsonable.register(NonEmptyString)
def _nonempty_string(obj: NonEmptyString) -> str:
    """``NonEmptyString`` (and its subclasses) become strings."""
    return str(obj)


@to_jsonable.register(Mapping)
def _mapping(obj: Mapping) -> dict:
    """Mappings become dicts with their values converted."""
    return {key: to_jsonable(value) for key, value in obj.items()}


@to_jsonable.register(list)
@to_jsonable.register(tuple)
@to_jsonable.register(set)
@to_jsonable.register(frozenset)
def _sequence(obj) -> list:
    """Sequences become lists with their items converted."""
    return [to_jsonable(item) for item in obj]
