from typing import Union, Iterator

def float_range(
        low: Union[int, float],
        high: Union[int, float],
        step: Union[int, float] = 1
) -> Iterator[float]:
    """Same a `range` but allows floating-point values."""
    current = float(low)
    while current < high:
        yield current
        current = current + step
