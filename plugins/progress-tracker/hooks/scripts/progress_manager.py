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
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Default paths
DEFAULT_CLAUDE_DIR = ".claude"
PROGRESS_JSON = "progress.json"
PROGRESS_MD = "progress.md"


def get_progress_dir():
    """Get the .claude directory path for progress tracking."""
    cwd = Path.cwd()
    claude_dir = cwd / DEFAULT_CLAUDE_DIR
    return claude_dir


def load_progress_json():
    """Load the progress.json file."""
    progress_dir = get_progress_dir()
    json_path = progress_dir / PROGRESS_JSON

    if not json_path.exists():
        return None

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_progress_json(data):
    """Save data to progress.json file."""
    progress_dir = get_progress_dir()
    json_path = progress_dir / PROGRESS_JSON

    # Ensure .claude directory exists
    progress_dir.mkdir(exist_ok=True)

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
    progress_dir.mkdir(exist_ok=True)

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
            print(f"Progress tracking already exists for project: {existing.get('project_name', 'Unknown')}")
            print("Use --force to re-initialize")
            return False

    # Create initial progress structure
    data = {
        "project_name": project_name,
        "created_at": datetime.now().isoformat() + "Z",
        "features": features or [],
        "current_feature_id": None
    }

    save_progress_json(data)

    # Create initial progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Initialized progress tracking for: {project_name}")
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
    print(f"**Status**: {completed}/{total} completed ({completed * 100 // total if total > 0 else 0}%)")

    if current_id:
        current_feature = next((f for f in features if f.get("id") == current_id), None)
        if current_feature:
            print(f"**Current Feature**: {current_feature.get('name', 'Unknown')} (in progress)")

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

    remaining = [f for f in features if not f.get("completed", False) and f.get("id") != current_id]
    if remaining:
        print("\n### Pending:")
        for f in remaining:
            print(f"  [ ] {f.get('name', 'Unknown')}")

    return True


def check():
    """
    Check if progress tracking exists and has incomplete features.
    Returns exit code 0 if tracking is complete or doesn't exist, 1 if incomplete.
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
        print(f"[Progress Tracker] Unfinished project detected: {project_name}")
        print(f"Progress: {completed}/{total} completed")
        print(f"Use '/prog' to view status or '/prog next' to continue")
        return 1

    return 0


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
    data["current_feature_id"] = None

    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Completed feature: {feature.get('name', 'Unknown')}")
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
        "completed": False
    }

    features.append(new_feature)
    save_progress_json(data)

    # Update progress.md
    md_content = generate_progress_md(data)
    save_progress_md(md_content)

    print(f"Added feature: {name} (ID: {new_id})")
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
        ""
    ]

    completed = [f for f in features if f.get("completed", False)]
    in_progress = [f for f in features if f.get("id") == current_id]
    pending = [f for f in features if not f.get("completed", False) and f.get("id") != current_id]

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
    init_parser.add_argument("--force", action="store_true", help="Force re-initialization")

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

    # Add feature command
    add_parser = subparsers.add_parser("add-feature", help="Add a new feature")
    add_parser.add_argument("name", help="Feature name")
    add_parser.add_argument("test_steps", nargs="+", help="Test steps for the feature")

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
        return complete_feature(args.feature_id)
    elif args.command == "add-feature":
        return add_feature(args.name, args.test_steps)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
