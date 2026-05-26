"""
lock_manager.py — File-lock primitives for progress state mutations.

Extracted from progress_manager.py (F18 modularization).
All callers remain in progress_manager.py; this module holds only the
lock mechanics.
"""
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

from prog_paths import get_state_dir

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROGRESS_LOCK_FILE = "progress.lock"
PROGRESS_LOCK_TIMEOUT_SECONDS = 10.0
PROGRESS_LOCK_POLL_INTERVAL_SECONDS = 0.05

# Per-process re-entrant lock state (keyed by resolved project root)
_PROGRESS_LOCK_HANDLES: Dict[Path, Any] = {}
_PROGRESS_LOCK_DEPTHS: Dict[Path, int] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _progress_lock_path(project_root: Path) -> Path:
    """Return the per-project progress lock file path."""
    root = project_root.resolve()
    progress_dir = get_state_dir(root)
    progress_dir.mkdir(parents=True, exist_ok=True)
    return progress_dir / PROGRESS_LOCK_FILE


def _acquire_progress_lock(
    timeout_seconds: float,
    project_root: Path,
) -> None:
    """Acquire a re-entrant cross-process lock for progress state mutations."""
    if fcntl is None:
        return

    root = project_root.resolve()
    depth = _PROGRESS_LOCK_DEPTHS.get(root, 0)
    handle = _PROGRESS_LOCK_HANDLES.get(root)

    if depth > 0 and handle is not None:
        _PROGRESS_LOCK_DEPTHS[root] = depth + 1
        return

    lock_path = _progress_lock_path(root)
    handle = open(lock_path, "a+", encoding="utf-8")
    start = time.monotonic()

    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _PROGRESS_LOCK_HANDLES[root] = handle
            _PROGRESS_LOCK_DEPTHS[root] = 1
            return
        except BlockingIOError:
            if time.monotonic() - start >= timeout_seconds:
                handle.close()
                raise TimeoutError(
                    f"Timed out acquiring progress lock after {timeout_seconds:.1f}s: {lock_path}"
                )
            time.sleep(PROGRESS_LOCK_POLL_INTERVAL_SECONDS)
        except Exception:
            handle.close()
            raise


def _release_progress_lock(project_root: Path) -> None:
    """Release the re-entrant progress lock."""
    if fcntl is None:
        return

    root = project_root.resolve()
    depth = _PROGRESS_LOCK_DEPTHS.get(root, 0)
    if depth <= 0:
        return

    depth -= 1
    _PROGRESS_LOCK_DEPTHS[root] = depth
    if depth > 0:
        return

    handle = _PROGRESS_LOCK_HANDLES.pop(root, None)
    _PROGRESS_LOCK_DEPTHS.pop(root, None)
    if handle is None:
        return

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


@contextmanager
def progress_transaction(
    timeout_seconds: float,
    project_root: Path,
):
    """Transactional guard for mutating progress state."""
    _acquire_progress_lock(timeout_seconds=timeout_seconds, project_root=project_root)
    try:
        yield
    finally:
        _release_progress_lock(project_root=project_root)
