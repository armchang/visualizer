import itertools
import importlib
from typing import Any, Dict, List, Tuple

def load_strategy_module(strategy_module_path: str):
    """
    Dynamically imports a strategy module by path string.
    Example: "strategies.trendline_break_retest"
    """
    # 1) importlib.import_module loads the python module at runtime.
    #    This lets you pick a strategy by name/config.
    return importlib.import_module(strategy_module_path)

def build_param_grid(search_criteria: Dict[str, List[Any]]) -> Tuple[List[str], List[tuple]]:
    """
    Builds a Cartesian product grid (param_grid) from a dict of lists.

    Example input:
        {"interval": ["4h"], "cooldown": [10, 15]}

    Output:
        keys = ["interval", "cooldown"]
        param_grid = [("4h", 10), ("4h", 15)]
    """

    # 1) Grab the parameter names (dict keys) in a stable order.
    #    NOTE: Python 3.7+ keeps insertion order for dicts, so your
    #    grid order will match the order you wrote inside search_criteria.
    keys = list(search_criteria.keys())

    # 2) Build a list of lists: each key maps to the list of candidate values.
    #    This becomes the input to itertools.product(*values).
    values = []
    for k in keys:
        v = search_criteria[k]

        # 2a) Safety check: every param must be a list/tuple of candidate values.
        if not isinstance(v, (list, tuple)):
            raise TypeError(
                f"search_criteria['{k}'] must be a list/tuple of values. Got: {type(v)}"
            )

        # 2b) Safety check: avoid empty arrays (it would produce zero combinations).
        if len(v) == 0:
            raise ValueError(f"search_criteria['{k}'] is empty. Provide at least 1 value.")

        # 2c) Store the candidate values list in the same order as keys.
        values.append(v)

    # 3) Cartesian product across all parameter value lists.
    #    This creates tuples aligned with `keys`.
    param_grid = list(itertools.product(*values))

    # 4) Return both the key order and the tuple grid.
    return keys, param_grid


def iter_param_dicts(search_criteria: Dict[str, List[Any]]):
    """
    Generator that yields each parameter combination as a dict instead of a tuple.

    This is often easier than dealing with tuple positions.
    """
    # 1) Build keys + tuple grid using the function above.
    keys, grid = build_param_grid(search_criteria)

    # 2) Convert each tuple combo into a dict {param_name: chosen_value}.
    for combo in grid:
        yield dict(zip(keys, combo))