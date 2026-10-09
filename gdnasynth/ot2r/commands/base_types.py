"""Base types used to build up the types we need."""


class NumericOpentronsVersion:
    """Specification for numeric Opentrons version values."""
    __slots__ = ("_value",)

    def __init__(self, value: int) -> None:
        """Initialise a numeric Opentrons version"""
        if value < 2:
            raise ValueError("NumericOpentronsVersion cannot be less than 2.")
        self._value = value

    def __repr__(self) -> str:
        """Representation for NumericOpentronsVersion"""
        return f"NumericOpentronsVersion({self._value})"

    def __str__(self) -> str:
        """Convert NumericOpentronsVersion value to string."""
        return str(self._value)


class NonEmptyString:
    """A Non-Empty string type."""
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        """Initialise a definition URI"""
        if not value:
            raise ValueError(
                f"{self.__class__.__name__} cannot be an empty string")
        self._value = value

    def __repr__(self) -> str:
        """Provide a representation output for the type."""
        return f"{self.__class__.__name__}({self._value!r})"

    def __str__(self) -> str:
        """Convert the value to its equivalent string."""
        return str(self._value)
