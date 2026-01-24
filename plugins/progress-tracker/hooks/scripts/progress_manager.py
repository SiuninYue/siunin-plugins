#!/usr/bin/env python3
"""
Progress Manager - Core state management for Progress Tracker plugin.

This script handles initialization, status checking, and state updates for
feature-based progress tracking.

Usage:
    python3 progress_manager.py init [--force] <project_name>
    python3 progress_manager.py status
    python3 progress_manager.py check
    python3 progress_manager.py set-current <feature_id>
    python3 progress_manager.py complete <feature_id>
    python3 progress_manager.py add-feature <name> <test_steps...>
    python3 progress_manager.py reset
"""

import argparse
import json
import os
import sys
import subprocess
import shutil
import logging
from datetime import datetime
from pathlib import Path

# Default paths
DEFAULT_CLAUDE_DIR = ".claude"
PROGRESS_JSON = "progress.json"
PROGRESS_MD = "progress.md"

# Configure logging for diagnostics
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


def get_plugin_root():
    """
    Get the plugin root directory with multiple fallback mechanisms.

    Priority:
    1. Environment variable CLAUDE_PLUGIN_ROOT
    2. Relative to script location (progress_manager.py)
    3. Common plugin installation paths

    Returns:
        Path: The plugin root directory

    Raises:
        RuntimeError: If plugin root cannot be determined
    """
    # 1. Try environment variable
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        root = Path(env_root)
        if validate_plugin_root(root):
            logger.info(f"Using CLAUDE_PLUGIN_ROOT: {root}")
            return root
        else:
            logger.warning(f"CLAUDE_PLUGIN_ROOT is set but invalid: {env_root}")

    # 2. Try relative to script location
    script_path = Path(__file__).resolve()
    # Script is at: <plugin_root>/hooks/scripts/progress_manager.py
    # So plugin root is 3 levels up
    relative_root = script_path.parent.parent.parent
    if validate_plugin_root(relative_root):
        logger.info(f"Using script-relative path: {relative_root}")
        return relative_root

    # 3. Try common installation paths
    common_paths = [
        # User-level plugin installation
        Path.home() / ".claude" / "plugins" / "progress-tracker",
        # System-wide plugin installation
        Path("/usr/local/lib/claude/plugins/progress-tracker"),
        # Development directory (when working on the plugin itself)
        Path(__file__).resolve().parent.parent.parent.parent.parent,
    ]

    for path in common_paths:
        if validate_plugin_root(path):
            logger.info(f"Using common path: {path}")
            return path

    # If all else fails, raise an error with helpful message
    raise RuntimeError(
        "Cannot determine plugin root directory. "
        "Set CLAUDE_PLUGIN_ROOT environment variable or ensure plugin is properly installed. "
        f"Searched: {env_root if env_root else 'not set'}, {relative_root}, {common_paths}"
    )


def validate_plugin_root(path):
    """
    Validate that a path is a valid plugin root directory.

    A valid plugin root should contain:
    - hooks/hooks.json or hooks/scripts/progress_manager.py
    - skills/ directory (optional but recommended)

    Args:
        path: Path to validate

    Returns:
        bool: True if path appears to be a valid plugin root
    """
    path = Path(path)

    # Check if path exists
    if not path.exists():
        return False

    # Check for key plugin files
    has_hooks_json = (path / "hooks" / "hooks.json").exists()
    has_progress_manager = (path / "hooks" / "scripts" / "progress_manager.py").exists()
    has_skills = (path / "skills").exists()
    has_commands = (path / "commands").exists()

    # At minimum, should have the progress_manager script
    if has_progress_manager:
        return True

    # Or hooks.json if using direct script loading
    if has_hooks_json and (has_skills or has_commands):
        return True

    return False


def find_project_root():
    """
    Find the project root directory.

    Priority:
    1. Git root
    2. Parent directory containing .claude
    3. Current working directory
    """
    cwd = Path.cwd()

    # Check for git root
    try:
        git_root = (
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL
            )
            .decode("utf-8")
            .strip()
        )
        return Path(git_root)
    except subprocess.CalledProcessError:
        pass

    # Check for existing .claude directory in parents
    current = cwd
    while current != current.parent:
        if (current / DEFAULT_CLAUDE_DIR).exists():
            return current
        current = current.parent

    return cwd


def get_progress_dir():
    """Get the .claude directory path for progress tracking."""
    root = find_project_root()
    claude_dir = root / DEFAULT_CLAUDE_DIR
    return claude_dir


def load_progress_json():
    """Load the progress.json file."""
    progress_dir = get_progress_dir()
    json_path = progress_dir / PROGRESS_JSON

    if not json_path.exists():
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Error: {json_path} is corrupted.")
        return None


def save_progress_json(data):
    """Save data to progress.json file."""
    progress_dir = get_progress_dir()
    json_path = progress_dir / PROGRESS_JSON

    # Ensure .claude directory exists
    progress_dir.mkdir(parents=True, exist_ok=True)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_progress_md():
    """Load the progress.md file content."""
    progress_dir = get_progress_dir()
    md_path = progress_dir / PROGRESS_MD

    if not md_path.exists():
        return None

    with open(md_path, "r", encoding="utf-8") as f:
        return f.read()


def save_progress_md(content):
    """Save content to progress.md file."""
    progress_dir = get_progress_dir()
    md_path = progress_dir / PROGRESS_MD

    # Ensure .claude directory exists
    progress_dir.mkdir(parents=True, exist_ok=True)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)


def init_tracking(project_name, features=None, force=False):
    """
    Initialize progress tracking for a project.

    Args:
        project_name: Name of the project to track
        features: Optional list of feature dicts with keys: name, test_steps
        force: Force re-initialization even if tracking exists
    """
    progress_dir = get_progress_dir()
    json_path = progress_dir / PROGRESS_JSON

    if json_path.exists() and not force:
        existing = load_progress_json()
        if existing:
            print(
                f"Progress tracking already exists for project: {existing.get('project_name', 'Unknown')}"
            )
            print(f"Location: {progress_dir}")
            print("Use --force to re-initialize")
            return False

    # Create initial progress structure
    data = {
        "project_name": project_name,
        "created_at": datetime.now().isoformat() + "Z",
        "features": features or [],
        "current_feature_id": None,
    }

    save_progress_json(data)

    # Create initial progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Initialized progress tracking for: {project_name}")
    print(f"Location: {progress_dir}")
    if features:
        print(f"Added {len(features)} features")
    return True


def status():
    """Display current progress status."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found. Use '/prog init' to start tracking.")
        return False

    project_name = data.get("project_name", "Unknown")
    features = data.get("features", [])
    current_id = data.get("current_feature_id")

    # Calculate statistics
    total = len(features)
    completed = sum(1 for f in features if f.get("completed", False))
    in_progress = current_id is not None

    print(f"\n## Project: {project_name}")
    print(
        f"**Status**: {completed}/{total} completed ({completed * 100 // total if total > 0 else 0}%)"
    )

    if current_id:
        current_feature = next((f for f in features if f.get("id") == current_id), None)
        if current_feature:
            print(
                f"**Current Feature**: {current_feature.get('name', 'Unknown')} (in progress)"
            )

    # Display features
    if completed > 0:
        print("\n### Completed:")
        for f in features:
            if f.get("completed", False):
                print(f"  [x] {f.get('name', 'Unknown')}")

    if in_progress:
        print("\n### In Progress:")
        for f in features:
            if f.get("id") == current_id:
                print(f"  [*] {f.get('name', 'Unknown')}")
                test_steps = f.get("test_steps", [])
                if test_steps:
                    print("     Test steps:")
                    for step in test_steps:
                        print(f"       - {step}")

    remaining = [
        f
        for f in features
        if not f.get("completed", False) and f.get("id") != current_id
    ]
    if remaining:
        print("\n### Pending:")
        for f in remaining:
            print(f"  [ ] {f.get('name', 'Unknown')}")

    return True


def check():
    """
    Check if progress tracking exists and has incomplete features.
    Returns exit code 0 if tracking is complete or doesn't exist, 1 if incomplete.

    Outputs JSON-formatted recovery information when incomplete work is detected.
    """
    data = load_progress_json()
    if not data:
        return 0  # No tracking = nothing to recover

    features = data.get("features", [])
    incomplete = [f for f in features if not f.get("completed", False)]

    if incomplete:
        project_name = data.get("project_name", "Unknown")
        total = len(features)
        completed = total - len(incomplete)
        current_id = data.get("current_feature_id")
        workflow_state = data.get("workflow_state", {})

        # If there's a feature in progress, provide detailed recovery info
        if current_id:
            feature = next((f for f in features if f.get("id") == current_id), None)
            if feature:
                phase = workflow_state.get("phase", "unknown")
                plan_path = workflow_state.get("plan_path", "")
                completed_tasks = workflow_state.get("completed_tasks", [])
                total_tasks = workflow_state.get("total_tasks", 0)

                # Determine recovery recommendation
                recommendation = determine_recovery_action(phase, feature, completed_tasks, total_tasks)

                recovery_info = {
                    "status": "incomplete",
                    "feature_id": current_id,
                    "feature_name": feature.get("name", "Unknown"),
                    "phase": phase,
                    "plan_path": plan_path,
                    "completed_tasks": completed_tasks,
                    "total_tasks": total_tasks,
                    "recommendation": recommendation
                }

                print(json.dumps(recovery_info))
                return 1

        # General incomplete status (no specific feature in progress)
        print(f"[Progress Tracker] Unfinished project detected: {project_name}")
        print(f"Progress: {completed}/{total} completed")
        print(f"Use '/prog' to view status or '/prog next' to continue")
        return 1

    return 0


def determine_recovery_action(phase, feature, completed_tasks, total_tasks):
    """Determine the recommended recovery action based on workflow state."""
    if phase == "execution_complete":
        return "run_prog_done"
    elif phase == "execution" and total_tasks > 0:
        progress = len(completed_tasks) / total_tasks if total_tasks > 0 else 0
        if progress >= 0.8:
            return "auto_resume"
        else:
            return "manual_resume"
    elif phase in ["planning", "design_complete", "design"]:
        return "restart_from_planning"
    else:
        return "manual_review"


def set_current(feature_id):
    """Set the current feature being worked on."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)

    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    data["current_feature_id"] = feature_id
    save_progress_json(data)

    print(f"Set current feature: {feature.get('name', 'Unknown')}")
    return True


def get_next_feature():
    """Get the next incomplete feature."""
    data = load_progress_json()
    if not data:
        return None

    features = data.get("features", [])
    for feature in features:
        if not feature.get("completed", False):
            return feature

    return None


def complete_feature(feature_id, commit_hash=None):
    """Mark a feature as completed."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)

    if not feature:
        print(f"Feature ID {feature_id} not found")
        return False

    feature["completed"] = True
    feature["completed_at"] = datetime.now().isoformat() + "Z"
    if commit_hash:
        feature["commit_hash"] = commit_hash

    data["current_feature_id"] = None

    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Completed feature: {feature.get('name', 'Unknown')}")
    if commit_hash:
        print(f"Recorded commit: {commit_hash}")
    return True


def undo_last_feature():
    """Undo the last completed feature, reverting git commit if recorded."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    features = data.get("features", [])
    completed_features = [f for f in features if f.get("completed", False)]

    if not completed_features:
        print("No completed features to undo.")
        return False

    # Sort by completed_at desc, then id desc
    def sort_key(f):
        # Use a default very old date for features without completed_at
        date_str = f.get("completed_at", "1970-01-01T00:00:00Z")
        return (date_str, f.get("id", 0))

    last_feature = sorted(completed_features, key=sort_key, reverse=True)[0]
    commit_hash = last_feature.get("commit_hash")

    print(
        f"Undoing feature: {last_feature.get('name', 'Unknown')} (ID: {last_feature.get('id')})"
    )

    # Attempt git revert if hash exists
    if commit_hash:
        print(f"Attempting to revert commit {commit_hash}...")
        try:
            # Check for working directory changes first
            status = subprocess.check_output(
                ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
            )
            if status:
                print(
                    "Error: Working directory is not clean. Commit or stash changes before undoing."
                )
                return False

            subprocess.check_call(
                ["git", "revert", "--no-edit", commit_hash],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            print(f"Successfully reverted commit {commit_hash}")
        except subprocess.CalledProcessError as e:
            print(f"Error reverting commit: {e}")
            print("To protect your repo, progress undo has been aborted.")
            return False
    else:
        print("No commit hash recorded for this feature. Skipping git revert.")

    # Update state
    last_feature["completed"] = False
    if "completed_at" in last_feature:
        del last_feature["completed_at"]
    if "commit_hash" in last_feature:
        del last_feature["commit_hash"]

    # If nothing is currently in progress, we could optionally set this as current
    # But for safety, we'll leave current_feature_id as None or whatever it was

    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print("Progress tracking updated.")
    return True


def add_feature(name, test_steps):
    """Add a new feature to the tracking."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found. Use init first.")
        return False

    features = data.get("features", [])

    # Generate new ID
    max_id = max([f.get("id", 0) for f in features], default=0)
    new_id = max_id + 1

    new_feature = {
        "id": new_id,
        "name": name,
        "test_steps": test_steps,
        "completed": False,
    }

    features.append(new_feature)
    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Added feature: {name} (ID: {new_id})")
    return True


def reset_tracking(force=False):
    """Reset progress tracking by removing the .claude directory."""
    progress_dir = get_progress_dir()
    if not progress_dir.exists():
        print("No progress tracking found to reset.")
        return True

    if not force:
        confirm = input(
            f"Are you sure you want to remove progress tracking at {progress_dir}? (y/N): "
        )
        if confirm.lower() != "y":
            print("Reset cancelled.")
            return False

    try:
        shutil.rmtree(progress_dir)
        print("Progress tracking reset successfully.")
        return True
    except Exception as e:
        print(f"Error resetting progress tracking: {e}")
        return False


def set_workflow_state(phase=None, plan_path=None, next_action=None):
    """Set workflow state for current feature."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    if not data.get("current_feature_id"):
        print("Error: No feature currently in progress")
        return False

    workflow_state = data.get("workflow_state", {})

    if phase:
        workflow_state["phase"] = phase
    if plan_path is not None:
        workflow_state["plan_path"] = plan_path
    if next_action:
        workflow_state["next_action"] = next_action

    workflow_state["updated_at"] = datetime.now().isoformat() + "Z"

    data["workflow_state"] = workflow_state
    save_progress_json(data)

    print(f"Workflow state updated: phase={phase or workflow_state.get('phase')}")
    return True


def update_workflow_task(task_id, status):
    """Update task completion status in workflow_state."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    workflow_state = data.get("workflow_state", {})

    if status == "completed":
        completed_tasks = workflow_state.get("completed_tasks", [])
        if task_id not in completed_tasks:
            completed_tasks.append(task_id)
            workflow_state["completed_tasks"] = completed_tasks
            workflow_state["current_task"] = task_id + 1

    workflow_state["updated_at"] = datetime.now().isoformat() + "Z"

    data["workflow_state"] = workflow_state
    save_progress_json(data)

    total = workflow_state.get("total_tasks", 0)
    print(f"Task {task_id}/{total} marked as {status}")
    return True


def clear_workflow_state():
    """Clear workflow state from progress tracking."""
    data = load_progress_json()
    if not data:
        print("No progress tracking found")
        return False

    if "workflow_state" in data:
        del data["workflow_state"]
        save_progress_json(data)
        print("Workflow state cleared")
        return True

    print("No workflow state to clear")
    return True


def generate_progress_md(data):
    """Generate markdown content from progress data."""
    project_name = data.get("project_name", "Unknown Project")
    features = data.get("features", [])
    current_id = data.get("current_feature_id")
    created_at = data.get("created_at", "")

    md_lines = [
        f"# Project Progress: {project_name}",
        "",
        f"**Created**: {created_at}",
        "",
    ]

    completed = [f for f in features if f.get("completed", False)]
    in_progress = [f for f in features if f.get("id") == current_id]
    pending = [
        f
        for f in features
        if not f.get("completed", False) and f.get("id") != current_id
    ]

    total = len(features)
    completed_count = len(completed)

    md_lines.append(f"**Status**: {completed_count}/{total} completed")
    md_lines.append("")

    if completed:
        md_lines.append("## Completed")
        for f in completed:
            md_lines.append(f"- [x] {f.get('name', 'Unknown')}")
        md_lines.append("")

    if in_progress:
        md_lines.append("## In Progress")
        for f in in_progress:
            md_lines.append(f"- [ ] {f.get('name', 'Unknown')}")
            test_steps = f.get("test_steps", [])
            if test_steps:
                md_lines.append("  **Test steps**:")
                for step in test_steps:
                    md_lines.append(f"  - {step}")
        md_lines.append("")

    if pending:
        md_lines.append("## Pending")
        for f in pending:
            md_lines.append(f"- [ ] {f.get('name', 'Unknown')}")
        md_lines.append("")

    return "\n".join(md_lines)


def main():
    parser = argparse.ArgumentParser(description="Progress Tracker Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize progress tracking")
    init_parser.add_argument("project_name", help="Name of the project")
    init_parser.add_argument(
        "--force", action="store_true", help="Force re-initialization"
    )

    # Status command
    subparsers.add_parser("status", help="Show progress status")

    # Check command
    subparsers.add_parser("check", help="Check for incomplete progress")

    # Set current command
    current_parser = subparsers.add_parser("set-current", help="Set current feature")
    current_parser.add_argument("feature_id", type=int, help="Feature ID")

    # Complete command
    complete_parser = subparsers.add_parser("complete", help="Mark feature as complete")
    complete_parser.add_argument("feature_id", type=int, help="Feature ID")
    complete_parser.add_argument("--commit", help="Git commit hash")

    # Add feature command
    add_parser = subparsers.add_parser("add-feature", help="Add a new feature")
    add_parser.add_argument("name", help="Feature name")
    add_parser.add_argument("test_steps", nargs="+", help="Test steps for the feature")

    # Undo command
    subparsers.add_parser("undo", help="Undo last completed feature")

    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset progress tracking")
    reset_parser.add_argument(
        "--force", action="store_true", help="Force reset without confirmation"
    )

    # Set workflow state command
    workflow_parser = subparsers.add_parser(
        "set-workflow-state", help="Set workflow state for current feature"
    )
    workflow_parser.add_argument("--phase", help="Workflow phase")
    workflow_parser.add_argument("--plan-path", help="Path to plan file")
    workflow_parser.add_argument("--next-action", help="Next action to take")

    # Update workflow task command
    task_parser = subparsers.add_parser(
        "update-workflow-task", help="Update task completion status"
    )
    task_parser.add_argument("task_id", type=int, help="Task ID")
    task_parser.add_argument("status", choices=["completed"], help="Task status")

    # Clear workflow state command
    subparsers.add_parser("clear-workflow-state", help="Clear workflow state")

    args = parser.parse_args()

    if args.command == "init":
        return init_tracking(args.project_name, force=args.force)
    elif args.command == "status":
        return status()
    elif args.command == "check":
        return check()
    elif args.command == "set-current":
        return set_current(args.feature_id)
    elif args.command == "complete":
        return complete_feature(args.feature_id, commit_hash=args.commit)
    elif args.command == "add-feature":
        return add_feature(args.name, args.test_steps)
    elif args.command == "undo":
        return undo_last_feature()
    elif args.command == "reset":
        return reset_tracking(force=args.force)
    elif args.command == "set-workflow-state":
        return set_workflow_state(
            phase=args.phase, plan_path=args.plan_path, next_action=args.next_action
        )
    elif args.command == "update-workflow-task":
        return update_workflow_task(args.task_id, args.status)
    elif args.command == "clear-workflow-state":
        return clear_workflow_state()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
