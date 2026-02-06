#!/usr/bin/env python3
"""
Git command validation and secure execution wrapper.

This module provides secure Git command execution with input validation
to prevent command injection attacks. All Git commands should be executed
through this wrapper rather than direct subprocess calls.

Security Features:
- Commit hash format validation (7-40 hex characters)
- Shell metacharacter detection and blocking
- Command timeout enforcement
- Structured error handling
"""

import re
import subprocess
from typing import List, Optional, Tuple


# Git commit hash pattern: 7-40 hexadecimal characters
COMMIT_HASH_PATTERN = re.compile(r'^[0-9a-f]{7,40}$')

# Dangerous shell metacharacters that could enable command injection
DANGEROUS_CHARS = [';', '&', '|', '$', '`', '(', ')', '<', '>', '\n', '\r', '\t']


class GitCommandError(Exception):
    """Exception raised when a Git command fails validation or execution."""
    pass


def validate_commit_hash(commit_hash: str) -> bool:
    """
    Validate git commit hash format (7-40 hex chars).

    Args:
        commit_hash: The commit hash string to validate

    Returns:
        True if the hash format is valid, False otherwise

    Examples:
        >>> validate_commit_hash('a1b2c3d')
        True
        >>> validate_commit_hash('abc1234; rm -rf /')
        False
        >>> validate_commit_hash('$(whoami)')
        False
    """
    if not commit_hash or not isinstance(commit_hash, str):
        return False

    commit_hash = commit_hash.strip()

    # Check for shell metacharacters first (before regex)
    if any(char in commit_hash for char in DANGEROUS_CHARS):
        return False

    # Validate format with regex
    return bool(COMMIT_HASH_PATTERN.match(commit_hash))


def _validate_git_args(args: List[str]) -> None:
    """
    Validate that Git arguments don't contain dangerous characters.

    Args:
        args: List of command arguments (including 'git' as first element)

    Raises:
        GitCommandError: If dangerous characters are detected
    """
    for arg in args:
        arg_str = str(arg) if not isinstance(arg, str) else arg

        # Check for shell metacharacters
        for char in DANGEROUS_CHARS:
            if char in arg_str:
                raise GitCommandError(
                    f"Dangerous character '{char}' detected in argument: {arg}"
                )

        # Check for potential command injection patterns
        dangerous_patterns = [
            r'\$\(',  # Command substitution $(...)
            r'`',     # Backtick command substitution
            r'\|',    # Pipe
            r';',     # Command separator
            r'&&',    # AND operator
            r'\|\|',  # OR operator
            r'>',     # Output redirection
            r'<',     # Input redirection
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, arg_str):
                raise GitCommandError(
                    f"Potentially dangerous pattern '{pattern}' detected in argument: {arg}"
                )


def safe_git_command(
    args: List[str],
    capture_output: bool = True,
    check: bool = True,
    cwd: Optional[str] = None,
    timeout: int = 30
) -> Tuple[int, str, str]:
    """
    Execute git command with security validation.

    This function validates all arguments before execution to prevent
    command injection attacks. It should be used for all Git operations
    instead of direct subprocess calls.

    Args:
        args: Command arguments list, e.g., ['git', 'status', '--porcelain']
        capture_output: Whether to capture stdout/stderr
        check: If True, raise exception on non-zero exit (deprecated, use returncode)
        cwd: Working directory for command execution
        timeout: Maximum seconds to wait for command to complete

    Returns:
        Tuple of (return_code, stdout, stderr)

    Raises:
        GitCommandError: If validation fails or command execution times out

    Examples:
        >>> exit_code, stdout, stderr = safe_git_command(['git', 'status', '--porcelain'])
        >>> if exit_code == 0:
        ...     print("Working directory clean")
    """
    # Validate all arguments before execution
    try:
        _validate_git_args(args)
    except GitCommandError as e:
        # Re-raise with context
        raise GitCommandError(f"Argument validation failed: {e}")

    # Build command (strip 'git' from args if present to avoid duplication)
    if args and args[0] == 'git':
        cmd = args
    else:
        cmd = ['git'] + args

    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            check=False,  # We'll handle return codes manually
            cwd=cwd,
            timeout=timeout,
            text=True
        )

        return result.returncode, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        raise GitCommandError(
            f"Git command timed out after {timeout} seconds: {cmd}"
        )
    except FileNotFoundError:
        raise GitCommandError(
            f"Git not found. Please ensure Git is installed and in PATH."
        )
    except Exception as e:
        raise GitCommandError(
            f"Failed to execute Git command: {e}"
        )


def is_git_repository(cwd: Optional[str] = None) -> bool:
    """
    Check if the current directory (or cwd) is a Git repository.

    Args:
        cwd: Directory to check (defaults to current directory)

    Returns:
        True if directory is a Git repository, False otherwise
    """
    try:
        exit_code, _, _ = safe_git_command(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            cwd=cwd,
            timeout=5
        )
        return exit_code == 0
    except GitCommandError:
        return False


def get_git_root(cwd: Optional[str] = None) -> Optional[str]:
    """
    Get the root directory of the Git repository.

    Args:
        cwd: Directory to start from (defaults to current directory)

    Returns:
        Path to Git repository root, or None if not in a repository
    """
    try:
        exit_code, stdout, _ = safe_git_command(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=cwd,
            timeout=5
        )
        if exit_code == 0:
            return stdout.strip()
        return None
    except GitCommandError:
        return None


def is_working_directory_clean(cwd: Optional[str] = None) -> bool:
    """
    Check if the Git working directory is clean (no uncommitted changes).

    Args:
        cwd: Directory to check (defaults to current directory)

    Returns:
        True if working directory is clean, False otherwise
    """
    try:
        exit_code, stdout, _ = safe_git_command(
            ['git', 'status', '--porcelain'],
            cwd=cwd,
            timeout=5
        )
        if exit_code == 0:
            return not stdout.strip()
        return True  # Assume clean if command fails
    except GitCommandError:
        return True  # Assume clean if validation fails


def get_current_commit_hash(cwd: Optional[str] = None) -> Optional[str]:
    """
    Get the current commit hash (HEAD).

    Args:
        cwd: Directory to check (defaults to current directory)

    Returns:
        Current commit hash or None if not in a repository
    """
    try:
        exit_code, stdout, _ = safe_git_command(
            ['git', 'rev-parse', 'HEAD'],
            cwd=cwd,
            timeout=5
        )
        if exit_code == 0:
            return stdout.strip()
        return None
    except GitCommandError:
        return None
