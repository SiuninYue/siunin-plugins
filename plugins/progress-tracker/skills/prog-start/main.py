#!/usr/bin/env python3
"""prog-start helper script: transition active feature to developing."""

import sys
from pathlib import Path


def _load_progress_manager():
    script_path = Path(__file__).resolve()
    plugin_root = script_path.parents[2]
    hooks_scripts = plugin_root / "hooks" / "scripts"
    sys.path.insert(0, str(hooks_scripts))
    import progress_manager  # pylint: disable=import-outside-toplevel
    return progress_manager


def main() -> int:
    progress_manager = _load_progress_manager()
    return 0 if progress_manager.set_development_stage("developing") else 1


if __name__ == "__main__":
    raise SystemExit(main())
