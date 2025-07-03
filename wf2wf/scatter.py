"""wf2wf.scatter – helper functions to expand CWL scatter specifications."""

from __future__ import annotations

from itertools import product
from typing import Any, Dict, List

__all__ = ["expand"]


def _dotproduct(names: List[str], values: List[List[Any]]):
    if len({len(v) for v in values}) != 1:
        raise ValueError("dotproduct scatter requires equal length arrays")
    for idx in range(len(values[0])):
        yield {n: v[idx] for n, v in zip(names, values)}


def _nested(names: List[str], values: List[List[Any]]):
    # Recursively nest the scatter dimensions
    def _rec(i: int, base: Dict[str, Any]):
        if i == len(names):
            yield base
            return
        for val in values[i]:
            new_base = base.copy()
            new_base[names[i]] = val
            yield from _rec(i + 1, new_base)

    yield from _rec(0, {})


def _flat(names: List[str], values: List[List[Any]]):
    for combo in product(*values):
        yield {n: v for n, v in zip(names, combo)}


_METHODS = {
    "dotproduct": _dotproduct,
    "nested_crossproduct": _nested,
    "flat_crossproduct": _flat,
}


def expand(
    scatter_spec: Dict[str, List[Any]], method: str = "dotproduct"
) -> List[Dict[str, Any]]:
    """Return a list of dictionaries representing each scatter binding.

    Parameters
    ----------
    scatter_spec
        Mapping from parameter name to its list of values.
    method
        One of ``dotproduct``, ``nested_crossproduct``, ``flat_crossproduct``.
    """

    names = list(scatter_spec.keys())
    values = list(scatter_spec.values())

    if method not in _METHODS:
        raise ValueError(f"Unknown scatter method '{method}'")

    result = list(_METHODS[method](names, values))
    return result
