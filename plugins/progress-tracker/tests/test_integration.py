#!/usr/bin/env python3
"""
Integration tests for progress-tracker plugin.

These tests cover the full workflow from initialization to feature completion,
including Git operations and security validations.
"""

import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# Add hooks/scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hooks', 'scripts'))

from git_validator import (
    validate_commit_hash,
    safe_git_command,
    GitCommandError,
    is_git_repository,
    is_working_directory_clean
)


class TestFullWorkflow:
    """Test complete workflow from init to feature completion."""

    def setup_method(self):
        """Create a temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.temp_dir)

        # Initialize git repo
        subprocess.run(['git', 'init'], capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], capture_output=True)

        # Path to progress_manager
        self.progress_manager = os.path.join(
            os.path.dirname(__file__),
            '..',
            'hooks',
            'scripts',
            'progress_manager.py'
        )

    def teardown_method(self):
        """Clean up temporary directory."""
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_to_complete(self):
        """Test complete workflow from init to feature completion."""
        # 1. Initialize tracking
        result = subprocess.run(
            ['python3', self.progress_manager, 'init', 'TestProject', '--force'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Verify progress.json exists
        progress_file = Path('.claude/progress.json')
        assert progress_file.exists(), "progress.json not created"

        # 2. Add a feature
        result = subprocess.run(
            ['python3', self.progress_manager, 'add-feature', 'Feature1', 'step1', 'step2'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Add feature failed: {result.stderr}"

        # 3. Set current feature
        result = subprocess.run(
            ['python3', self.progress_manager, 'set-current', '1'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Set current failed: {result.stderr}"

        # 4. Complete the feature
        result = subprocess.run(
            ['python3', self.progress_manager, 'complete', '1', '--skip-archive'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Complete failed: {result.stderr}"

        # Verify feature is marked complete
        with open(progress_file, 'r') as f:
            data = json.load(f)

        features = data.get('features', [])
        assert len(features) == 1, "Should have 1 feature"
        assert features[0]['completed'] is True, "Feature should be completed"
        assert features[0]['id'] == 1, "Feature ID should be 1"

    def test_add_multiple_features(self):
        """Test adding and tracking multiple features."""
        # Initialize
        subprocess.run(
            ['python3', self.progress_manager, 'init', 'MultiTest', '--force'],
            capture_output=True
        )

        # Add three features
        for i in range(1, 4):
            result = subprocess.run(
                ['python3', self.progress_manager, 'add-feature',
                 f'Feature{i}', f'step{i}a', f'step{i}b'],
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Failed to add feature {i}"

        # Check status
        result = subprocess.run(
            ['python3', self.progress_manager, 'status'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        # Verify in progress.json
        with open('.claude/progress.json', 'r') as f:
            data = json.load(f)

        features = data.get('features', [])
        assert len(features) == 3, "Should have 3 features"

        # Check IDs are sequential
        ids = [f['id'] for f in features]
        assert ids == [1, 2, 3], "Feature IDs should be 1, 2, 3"

    def test_bug_tracking_workflow(self):
        """Test bug tracking from addition to fix."""
        # Initialize
        subprocess.run(
            ['python3', self.progress_manager, 'init', 'BugTest', '--force'],
            capture_output=True
        )

        # Add a bug
        result = subprocess.run(
            ['python3', self.progress_manager, 'add-bug',
             '--description', 'Test bug description',
             '--priority', 'high'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Add bug failed: {result.stderr}"

        # Verify bug in progress.json
        with open('.claude/progress.json', 'r') as f:
            data = json.load(f)

        bugs = data.get('bugs', [])
        assert len(bugs) == 1, "Should have 1 bug"
        assert bugs[0]['description'] == 'Test bug description'
        assert bugs[0]['priority'] == 'high'

        # Update bug status
        bug_id = bugs[0]['id']
        result = subprocess.run(
            ['python3', self.progress_manager, 'update-bug',
             '--bug-id', bug_id,
             '--status', 'fixed',
             '--fix-summary', 'Fixed by removing extra space'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Update bug failed: {result.stderr}"

    def test_workflow_state_tracking(self):
        """Test workflow state updates during feature implementation."""
        # Initialize and add feature
        subprocess.run(['python3', self.progress_manager, 'init', 'WorkflowTest', '--force'],
                      capture_output=True)
        subprocess.run(['python3', self.progress_manager, 'add-feature', 'Feature1', 'step1'],
                      capture_output=True)
        subprocess.run(['python3', self.progress_manager, 'set-current', '1'],
                      capture_output=True)

        # Set workflow state
        result = subprocess.run(
            ['python3', self.progress_manager, 'set-workflow-state',
             '--phase', 'planning',
             '--plan-path', 'docs/plans/test.md',
             '--next-action', 'execution'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        # Verify workflow state
        with open('.claude/progress.json', 'r') as f:
            data = json.load(f)

        workflow_state = data.get('workflow_state', {})
        assert workflow_state['phase'] == 'planning'
        assert workflow_state['plan_path'] == 'docs/plans/test.md'
        assert workflow_state['next_action'] == 'execution'

        # Update task completion
        result = subprocess.run(
            ['python3', self.progress_manager, 'update-workflow-task', '1', 'completed'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        # Verify task update
        with open('.claude/progress.json', 'r') as f:
            data = json.load(f)

        workflow_state = data.get('workflow_state', {})
        assert 1 in workflow_state.get('completed_tasks', [])


class TestGitSecurity:
    """Test Git security validations."""

    def test_validate_commit_hash(self):
        """Test commit hash validation."""
        # Valid hashes
        assert validate_commit_hash('a1b2c3d') is True
        assert validate_commit_hash('a1b2c3d4e5f6789012345678901234567890abcd') is True
        assert validate_commit_hash('ABC1234') is True

        # Invalid hashes
        assert validate_commit_hash('') is False
        assert validate_commit_hash('abc123') is False  # Too short
        assert validate_commit_hash('g123456') is False  # Invalid char
        assert validate_commit_hash('abc1234; rm -rf /') is False  # Injection

    def test_blocks_command_injection(self):
        """Test that command injection attempts are blocked."""
        # Semicolon injection
        with pytest.raises(GitCommandError):
            safe_git_command(['git', 'status', ';', 'echo', 'hacked'])

        # Pipe injection
        with pytest.raises(GitCommandError):
            safe_git_command(['git', 'log', '|', 'cat', '/etc/passwd'])

        # Command substitution
        with pytest.raises(GitCommandError):
            safe_git_command(['git', 'status', '$(whoami)'])

    def test_rejects_dangerous_patterns(self):
        """Test rejection of various dangerous patterns."""
        dangerous_inputs = [
            'abc1234 && echo hacked',
            'abc1234 || echo hacked',
            'abc1234 > /tmp/pwn',
            'abc1234 < /etc/passwd',
            'abc1234`whoami`',
            'abc1234$(rm -rf /)',
        ]

        for test_input in dangerous_inputs:
            assert validate_commit_hash(test_input) is False, \
                f"Should reject dangerous input: {test_input}"

    def test_safe_git_command_valid(self):
        """Test that valid Git commands work."""
        exit_code, stdout, stderr = safe_git_command(['git', '--version'])
        assert exit_code == 0
        assert 'git version' in stdout.lower()


class TestComplexityAnalyzer:
    """Test complexity analysis with caching."""

    def setup_method(self):
        """Setup analyzer with temp cache dir."""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.temp_dir)

        # Import here to avoid issues if module not available
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hooks', 'scripts'))
        from complexity_analyzer import ComplexityAnalyzer
        self.ComplexityAnalyzer = ComplexityAnalyzer

    def teardown_method(self):
        """Clean up temp dir."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_simple_complexity(self):
        """Test detection of simple features."""
        analyzer = self.ComplexityAnalyzer(cache_dir=self.cache_dir)

        complexity, reason, metrics = analyzer.analyze_complexity(
            "Fix typo in README",
            ["Verify typo is fixed", "Check spelling"]
        )

        assert complexity == 'simple'
        assert metrics['num_steps'] == 2
        assert metrics['estimated_files'] <= 2

    def test_standard_complexity(self):
        """Test detection of standard features."""
        analyzer = self.ComplexityAnalyzer(cache_dir=self.cache_dir)

        complexity, reason, metrics = analyzer.analyze_complexity(
            "Implement user registration API endpoint",
            [
                "Test POST to /api/register with valid data",
                "Test duplicate email returns 400",
                "Verify password hashing",
                "Test user record is created",
                "Test validation errors"
            ]
        )

        assert complexity in ['standard', 'complex']
        assert metrics['num_steps'] == 5
        assert metrics['has_api'] is True

    def test_complex_complexity(self):
        """Test detection of complex features."""
        analyzer = self.ComplexityAnalyzer(cache_dir=self.cache_dir)

        complexity, reason, metrics = analyzer.analyze_complexity(
            "Refactor authentication system to support OAuth2 and JWT with distributed session management",
            [
                "Design OAuth2 flow architecture",
                "Implement JWT token service",
                "Add distributed session store",
                "Migrate existing users",
                "Test multiple provider support",
                "Verify token refresh flow",
                "Test session invalidation",
                "Performance test with 1000 concurrent users"
            ]
        )

        assert complexity == 'complex'
        assert metrics['design_score'] >= 1
        assert metrics['complex_score'] >= 1

    def test_cache_functionality(self):
        """Test that caching works correctly."""
        analyzer = self.ComplexityAnalyzer(cache_dir=self.cache_dir)

        desc = "Test feature for caching"
        steps = ["step1", "step2", "step3"]

        # First call - not cached
        complexity1, _, _ = analyzer.analyze_complexity(desc, steps, use_cache=True)

        # Second call - should be cached
        complexity2, _, _ = analyzer.analyze_complexity(desc, steps, use_cache=True)

        assert complexity1 == complexity2

        # Verify cache was created
        cache_file = self.cache_dir / "complexity_cache.json"
        assert cache_file.exists()

    def test_cache_expiration(self):
        """Test that expired cache entries are not used."""
        import time
        analyzer = self.ComplexityAnalyzer(cache_dir=self.cache_dir)

        desc = "Test cache expiration"
        steps = ["step1"]

        # Create cache entry
        complexity1, _, _ = analyzer.analyze_complexity(desc, steps, use_cache=True)

        # Manually expire the cache by modifying timestamp
        cache_file = self.cache_dir / "complexity_cache.json"
        with open(cache_file, 'r') as f:
            cache = json.load(f)

        # Set timestamp to old date
        old_key = list(cache.keys())[0]
        cache[old_key]['timestamp'] = '2020-01-01T00:00:00'

        with open(cache_file, 'w') as f:
            json.dump(cache, f)

        # Create new analyzer instance (should ignore expired cache)
        new_analyzer = self.ComplexityAnalyzer(cache_dir=self.cache_dir)
        stats = new_analyzer.get_cache_stats()

        # Expired entry should have been filtered out
        assert stats['entries'] == 0


class TestHealthCheck:
    """Test health check functionality."""

    def setup_method(self):
        """Create temp directory and initialize git."""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.temp_dir)

        subprocess.run(['git', 'init'], capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], capture_output=True)

        self.progress_manager = os.path.join(
            os.path.dirname(__file__),
            '..',
            'hooks',
            'scripts',
            'progress_manager.py'
        )

    def teardown_method(self):
        """Clean up."""
        import shutil
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_health_check_returns_json(self):
        """Test that health check returns valid JSON."""
        # Initialize tracking
        subprocess.run(['python3', self.progress_manager, 'init', 'HealthTest', '--force'],
                      capture_output=True)

        # Run health check
        result = subprocess.run(
            ['python3', self.progress_manager, 'health'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0

        # Verify JSON output
        health_data = json.loads(result.stdout)
        assert 'status' in health_data
        assert 'response_time_ms' in health_data
        assert 'recommended_timeout' in health_data

    def test_health_check_without_tracking(self):
        """Test health check when no tracking exists."""
        result = subprocess.run(
            ['python3', self.progress_manager, 'health'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0

        health_data = json.loads(result.stdout)
        # Should still be healthy even without tracking
        assert health_data['status'] in ['healthy', 'degraded']


# Performance tests
class TestPerformance:
    """Performance-related tests."""

    def test_complexity_analysis_performance(self):
        """Test that complexity analysis is fast with caching."""
        import time
        import tempfile
        import shutil
        from pathlib import Path

        temp_dir = tempfile.mkdtemp()
        cache_dir = Path(temp_dir)

        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hooks', 'scripts'))
            from complexity_analyzer import ComplexityAnalyzer

            analyzer = ComplexityAnalyzer(cache_dir=cache_dir)

            desc = "Performance test feature"
            steps = [f"step{i}" for i in range(10)]

            # Cold start
            start = time.time()
            analyzer.analyze_complexity(desc, steps, use_cache=True)
            cold_time = time.time() - start

            # Warm start (cached)
            start = time.time()
            analyzer.analyze_complexity(desc, steps, use_cache=True)
            warm_time = time.time() - start

            # Warm should be faster than cold
            # (Though both should be fast)
            assert cold_time < 1.0, f"Cold start too slow: {cold_time}s"
            assert warm_time < 0.1, f"Cached lookup too slow: {warm_time}s"

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


def run_tests():
    """Run all tests and report results."""
    import pytest

    # Run pytest with verbose output
    exit_code = pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '--color=yes'
    ])

    return exit_code


if __name__ == "__main__":
    # Add pytest import for test class decorators
    import pytest

    sys.exit(run_tests())
