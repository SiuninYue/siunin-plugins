#!/usr/bin/env python3
"""
Unit tests for git_validator module.

Tests security validation, command injection prevention, and
edge cases for Git command execution.
"""

import pytest
import sys
import os

# Add hooks/scripts to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hooks', 'scripts'))

from git_validator import (
    validate_commit_hash,
    safe_git_command,
    GitCommandError,
    is_git_repository,
    get_git_root,
    is_working_directory_clean,
    get_current_commit_hash
)


class TestCommitHashValidation:
    """Test commit hash format validation."""

    def test_valid_short_hash(self):
        """Valid 7-character hash should pass."""
        assert validate_commit_hash("a1b2c3d") is True

    def test_valid_full_hash(self):
        """Valid 40-character hash should pass."""
        assert validate_commit_hash("a1b2c3d4e5f6789012345678901234567890abcd") is True

    def test_valid_medium_hash(self):
        """Valid medium-length hash should pass."""
        assert validate_commit_hash("abc123456789") is True

    def test_empty_hash(self):
        """Empty hash should fail."""
        assert validate_commit_hash("") is False
        assert validate_commit_hash(None) is False

    def test_too_short_hash(self):
        """Hash with less than 7 characters should fail."""
        assert validate_commit_hash("abc123") is False

    def test_too_long_hash(self):
        """Hash with more than 40 characters should fail."""
        assert validate_commit_hash("a" * 41) is False

    def test_invalid_characters(self):
        """Hash with non-hex characters should fail."""
        assert validate_commit_hash("g1b2c3d") is False
        assert validate_commit_hash("abc123g") is False


class TestSecurityValidation:
    """Test security validation against command injection."""

    def test_rejects_semicolon_injection(self):
        """Should reject semicolon command injection."""
        assert validate_commit_hash("abc1234; rm -rf /") is False

    def test_rejects_pipe_injection(self):
        """Should reject pipe command injection."""
        assert validate_commit_hash("abc1234|cat /etc/passwd") is False

    def test_rejects_command_substitution_dollar(self):
        """Should reject $(...) command substitution."""
        assert validate_commit_hash("$(whoami)") is False
        assert validate_commit_hash("abc$(rm -rf /)") is False

    def test_rejects_backtick_injection(self):
        """Should reject backtick command substitution."""
        assert validate_commit_hash("`touch /tmp/pwn`") is False
        assert validate_commit_hash("abc`whoami`") is False

    def test_rejects_and_operator_injection(self):
        """Should reject AND operator injection."""
        assert validate_commit_hash("abc1234 && echo hacked") is False

    def test_rejects_or_operator_injection(self):
        """Should reject OR operator injection."""
        assert validate_commit_hash("abc1234 || echo hacked") is False

    def test_rejects_redirection_injection(self):
        """Should reject output redirection injection."""
        assert validate_commit_hash("abc1234 > /tmp/pwn") is False
        assert validate_commit_hash("abc1234 < /etc/passwd") is False

    def test_rejects_newline_injection(self):
        """Should reject newline injection."""
        assert validate_commit_hash("abc1234\necho hacked") is False
        assert validate_commit_hash("abc1234\recho hacked") is False

    def test_rejects_tab_injection(self):
        """Should reject tab injection (sanitization)."""
        assert validate_commit_hash("abc1234\techo hacked") is False

    def test_rejects_parentheses_injection(self):
        """Should reject parentheses in injection attempts."""
        assert validate_commit_hash("abc(1234)") is False


class TestSafeGitCommand:
    """Test safe_git_command function."""

    def test_rejects_dangerous_commands(self):
        """Should raise error for commands with dangerous characters."""
        with pytest.raises(GitCommandError, match="Dangerous character"):
            safe_git_command(['git', 'status', ';', 'echo', 'hacked'])

    def test_rejects_pipe_in_command(self):
        """Should raise error for commands with pipe."""
        with pytest.raises(GitCommandError):
            safe_git_command(['git', 'log', '|', 'grep', 'secret'])

    def test_rejects_command_substitution(self):
        """Should raise error for command substitution patterns."""
        with pytest.raises(GitCommandError):
            safe_git_command(['git', 'status', '$(whoami)'])

    def test_allows_valid_git_status(self):
        """Should allow valid git status command."""
        exit_code, stdout, stderr = safe_git_command(['git', 'status', '--porcelain'], timeout=5)
        # Should not raise an error
        assert exit_code in (0, 128)  # 0 = success, 128 = not in git repo

    def test_allows_valid_git_rev_parse(self):
        """Should allow valid git rev-parse command."""
        exit_code, stdout, stderr = safe_git_command(['git', 'rev-parse', '--git-dir'], timeout=5)
        # Should not raise an error
        assert exit_code in (0, 128)

    def test_timeout_enforcement(self):
        """Should enforce timeout on long-running commands."""
        # This test uses a short timeout
        with pytest.raises(GitCommandError, match="timed out"):
            # Simulate a long-running operation with a very short timeout
            # Note: This might not always timeout depending on system speed
            safe_git_command(['git', 'status'], timeout=0.0001)


class TestHelperFunctions:
    """Test helper functions in git_validator."""

    def test_is_git_repository(self):
        """Should detect if current directory is a git repository."""
        # Result depends on whether tests are run in a git repo
        result = is_git_repository()
        assert isinstance(result, bool)

    def test_get_git_root(self):
        """Should return git root or None."""
        result = get_git_root()
        assert result is None or isinstance(result, str)

    def test_is_working_directory_clean(self):
        """Should check if working directory is clean."""
        result = is_working_directory_clean()
        assert isinstance(result, bool)

    def test_get_current_commit_hash(self):
        """Should get current commit or None."""
        result = get_current_commit_hash()
        assert result is None or isinstance(result, str)
        if result:
            assert len(result) == 40  # Full hash


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_whitespace_in_hash(self):
        """Should reject hash with whitespace."""
        assert validate_commit_hash("abc 1234") is False
        assert validate_commit_hash(" abc1234") is False
        assert validate_commit_hash("abc1234 ") is False

    def test_unicode_in_hash(self):
        """Should reject hash with unicode characters."""
        assert validate_commit_hash("abc1234中文") is False

    def test_special_characters_in_hash(self):
        """Should reject hash with special characters."""
        assert validate_commit_hash("abc-1234") is False
        assert validate_commit_hash("abc_1234") is False
        assert validate_commit_hash("abc.1234") is False

    def test_mixed_case_hash(self):
        """Should accept uppercase hex characters."""
        assert validate_commit_hash("ABC1234") is True
        assert validate_commit_hash("AaBbCc1234") is True


class TestIntegrationScenarios:
    """Test real-world usage scenarios."""

    def test_undo_scenario_with_valid_hash(self):
        """Simulate undo operation with valid commit hash."""
        valid_hash = "a1b2c3d"
        assert validate_commit_hash(valid_hash) is True

    def test_undo_scenario_with_injection_attempt(self):
        """Simulate undo operation with injection attempt."""
        injection_hash = "a1b2c3d; rm -rf /"
        assert validate_commit_hash(injection_hash) is False

    def test_undo_scenario_with_command_substitution(self):
        """Simulate undo with command substitution attempt."""
        injection_hash = "$(cat ~/.ssh/id_rsa)"
        assert validate_commit_hash(injection_hash) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
