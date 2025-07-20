from typing import Any


def get_name(obj: Any) -> str:
    """Attempt to fetch a human readable name for an object"""
    if (name := getattr(obj, "__name__", None)) is not None:
        return name
    elif (cls := getattr(obj, "__class__", None)) is not None:
        return getattr(cls, "__name__", str(obj))
    return str(obj)
