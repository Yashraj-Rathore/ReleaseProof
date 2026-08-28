"""Explicit unsupported dynamic-import fixture."""

import importlib
from types import ModuleType


def load_plugin(name: str) -> ModuleType:
    return importlib.import_module(name)
