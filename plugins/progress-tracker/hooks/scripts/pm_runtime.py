"""
pm_runtime.py - resolve the live progress_manager module safely.

When the CLI is executed as ``python progress_manager.py``, the configured
module is ``__main__`` rather than ``progress_manager``. Extracted helper
modules must bind to that live module so --project-root scope and test patches
remain effective.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


def get_progress_manager_module() -> ModuleType:
    """Return the active progress_manager module, preferring CLI __main__."""
    main = sys.modules.get("__main__")
    main_file = getattr(main, "__file__", None)
    if (
        main is not None
        and main_file
        and Path(str(main_file)).name == "progress_manager.py"
        and hasattr(main, "find_project_root")
    ):
        return main

    loaded = sys.modules.get("progress_manager")
    if loaded is not None:
        return loaded
    return importlib.import_module("progress_manager")
