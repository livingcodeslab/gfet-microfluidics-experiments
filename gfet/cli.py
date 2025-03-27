"""Command-line utilities"""

def fetch_range_float(value: str) -> tuple[float, float, float]:
    """Convert a string into a tuple of values."""
    items = value.split(",")
    if len(items) not in (2, 3):
        raise ValueError(
            "Invalid range value. Expected two comma-separated values.")

    items = tuple(float(item) for item in items)
    if len(items) == 2:
        items = items + (0.1,)
    if items[0] < items[1]:
        return items
    return (items[1], items[0], items[2])
