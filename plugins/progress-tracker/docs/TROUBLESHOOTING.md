# Progress Tracker - Troubleshooting Guide

This guide helps you diagnose and resolve common issues with the Progress Tracker plugin.

## Table of Contents

1. [Initialization Issues](#initialization-issues)
2. [Git-Related Problems](#git-related-problems)
3. [Hook Timeout Issues](#hook-timeout-issues)
4. [Superpowers Integration](#superpowers-integration)
5. [Performance Issues](#performance-issues)
6. [Data Corruption](#data-corruption)
7. [Workflow Recovery](#workflow-recovery)

---

## Initialization Issues

### "No progress tracking found"

**Symptoms**: `/prog status` shows "No progress tracking found"

**Possible Causes**:
1. Never initialized tracking in this directory
2. Working in wrong directory
3. `.claude/` directory was deleted

**Solutions**:

```bash
# Check if progress.json exists
ls -la .claude/progress.json

# If not found, initialize tracking
/prog init <project-name>

# Or check parent directories
find . -name "progress.json" -type f
```

### "Progress tracking already exists"

**Symptoms**: `/prog init` fails saying tracking already exists

**Solution**:
```bash
# View existing progress
/prog status

# To re-initialize (WARNING: deletes existing data)
/prog reset --force
/prog init <new-project-name> --force
```

---

## Git-Related Problems

### "Invalid commit hash format"

**Symptoms**: Undo operation fails with commit hash error

**Possible Causes**:
1. Corrupted commit hash in progress.json
2. Manually edited hash with invalid format

**Solutions**:

```bash
# Check the commit hash format
python3 -c "
from hooks.scripts.git_validator import validate_commit_hash
print(validate_commit_hash('your_hash_here'))
"

# Valid format: 7-40 hex characters
# Examples: a1b2c3d, abc123456789, a1b2c3d4e5f6789012345678901234567890abcd
```

**Prevention**: Never manually edit commit hashes in progress.json

### "Git working directory not clean"

**Symptoms**: Cannot undo feature due to uncommitted changes

**Solution**:
```bash
# Check git status
git status

# Options:
# 1. Commit changes
git add .
git commit -m "WIP: save current work"

# 2. Stash changes
git stash

# 3. Discard changes (DANGER!)
git reset --hard HEAD

# Then retry undo
/prog undo
```

### "Git not found" error

**Symptoms**: Commands fail with "Git not found" message

**Solutions**:

```bash
# Check if git is installed
which git
git --version

# If not installed:
# macOS: xcode-select --install
# Ubuntu: sudo apt-get install git
# Windows: Download from git-scm.com
```

### "Git command timed out"

**Symptoms**: Git operations hang or timeout after 30 seconds

**Possible Causes**:
1. Large repository (100,000+ files)
2. Slow network (for remote operations)
3. Git hooks running slowly

**Solutions**:

```bash
# Run health check to get recommended timeout
python3 hooks/scripts/progress_manager.py health

# If recommended timeout > 30, edit hooks.json:
# Change "timeout": 30000 to higher value (in milliseconds)

# Example for 60 seconds:
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "command": "...",
        "timeout": 60000  # 60 seconds
      }]
    }]
  }
}
```

---

## Hook Timeout Issues

### "Hook timeout exceeded"

**Symptoms**: Claude Code shows "Hook timeout exceeded" on session start

**Root Cause**: Progress check takes longer than configured timeout

**Diagnosis**:
```bash
# Run health check
python3 hooks/scripts/progress_manager.py health

# Look at "response_time_ms" and "recommended_timeout"
```

**Solutions**:

1. **Increase timeout** (recommended):
```json
// In hooks/hooks.json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/progress_manager.py check",
        "timeout": 60000  // Increase as needed (in milliseconds)
      }]
    }]
  }
}
```

2. **Reduce feature count**:
```bash
# Archive completed features
/prog done  # Completes current feature

# Or start a new project for remaining work
/prog init "<project-name>-phase2"
```

3. **Clear cache**:
```bash
rm .claude/.cache/complexity_cache.json
```

---

## Superpowers Integration

### "Superpowers skills not available"

**Symptoms**: Feature implementation skips Superpowers workflow

**Possible Causes**:
1. Superpowers plugin not installed
2. Skills not loaded
3. Version incompatibility

**Solutions**:

1. **Check Superpowers installation**:
```bash
# List available skills
/skills

# Look for superpowers:* skills
```

2. **Install Superpowers**:
```bash
# Install from marketplace
/plugin install superpowers
```

3. **Use fallback workflow**:
- Progress Tracker will automatically fall back to manual implementation
- Follow the guided TDD steps provided
- Manual testing is required

### "Skill invocation failed"

**Symptoms**: Feature implementation stops with skill error

**Possible Causes**:
1. Skill not found
2. Skill crashed
3. Network issue (for remote skills)

**Solutions**:

```bash
# Check skill status
/skills

# Try manual invocation
/skill superpowers:test-driven-development "test description"

# If persistent, use fallback:
/prog next  # Will prompt for fallback
```

---

## Performance Issues

### "Complexity analysis is slow"

**Symptoms**: `/prog next` takes >5 seconds to start

**Solutions**:

1. **Check cache**:
```bash
# View cache stats
python3 -c "
import sys
sys.path.insert(0, 'hooks/scripts')
from complexity_analyzer import ComplexityAnalyzer
analyzer = ComplexityAnalyzer()
import json
print(json.dumps(analyzer.get_cache_stats(), indent=2))
"
```

2. **Clear old cache**:
```bash
rm .claude/.cache/complexity_cache.json
```

3. **Disable caching temporarily**:
- Edit complexity_analyzer.py
- Set `use_cache=False` in `analyze_complexity()` calls

### "Large project slowdown"

**Symptoms**: Operations slow with 50+ features

**Solutions**:

1. **Archive completed features**:
```bash
# Complete and archive features
/prog done  # For each completed feature

# Move to new project for next phase
/prog init "project-phase2"
```

2. **Split project**:
```bash
# Export current features
jq '.features' .claude/progress.json > features-backup.json

# Start fresh with remaining features
/prog reset
/prog init "project-remaining"
# Re-add pending features
```

---

## Data Corruption

### "progress.json is corrupted"

**Symptoms**: JSON decode error, malformed data

**Symptoms**:
- `Error: .claude/progress.json is corrupted`
- `JSONDecodeError`

**Solutions**:

1. **Check backup**:
```bash
# Git history
git log --follow .claude/progress.json

# Recover from last known good version
git checkout HEAD~1 -- .claude/progress.json
```

2. **Manual repair**:
```bash
# Validate JSON
python3 -m json.tool .claude/progress.json

# Fix syntax errors (missing commas, brackets, etc.)
# Use JSON linter
```

3. **Recover from progress.md**:
```bash
# progress.md is human-readable
cat .claude/progress.md

# Manually reconstruct progress.json based on progress.md content
```

4. **Last resort - reset**:
```bash
/prog reset --force
/prog init <project-name>
# Re-enter features manually
```

### "Duplicate bug detected"

**Symptoms**: Cannot add bug that already exists

**Solutions**:

1. **Check existing bugs**:
```bash
/prog fix --list
```

2. **Update existing bug**:
```bash
/prog fix --update-bug BUG-XXX --status confirmed
```

3. **Remove false positive**:
```bash
/prog fix --remove-bug BUG-XXX
```

---

## Workflow Recovery

### "Unfinished work detected"

**Symptoms**: Session start shows incomplete feature

**Solutions**:

1. **Continue current feature**:
```bash
/prog next  # Resume implementation
```

2. **Complete and skip**:
```bash
/prog done --skip-tests  # Mark complete (if actually done)
```

3. **Reset workflow state**:
```bash
python3 hooks/scripts/progress_manager.py clear-workflow-state
```

### "Feature implementation stuck"

**Symptoms**: Cannot proceed with feature implementation

**Solutions**:

1. **Check workflow state**:
```bash
python3 -c "
import json
data = json.load(open('.claude/progress.json'))
print(json.dumps(data.get('workflow_state', {}), indent=2))
"
```

2. **Clear stuck state**:
```bash
python3 hooks/scripts/progress_manager.py clear-workflow-state
/prog next  # Restart implementation
```

3. **Skip to completion**:
```bash
/prog done  # If implementation is actually done
```

---

## Diagnostic Commands

### Health Check

```bash
python3 hooks/scripts/progress_manager.py health
```

Output:
```json
{
  "status": "healthy",
  "response_time_ms": 45,
  "git_healthy": true,
  "data_valid": true,
  "recommended_timeout": 10
}
```

### Validate Git Validator

```bash
python3 -c "
import sys
sys.path.insert(0, 'hooks/scripts')
from git_validator import validate_commit_hash, safe_git_command

# Test validation
print('Hash validation:', validate_commit_hash('abc1234'))

# Test git command
exit_code, stdout, stderr = safe_git_command(['git', '--version'])
print('Git version:', stdout.strip())
"
```

### Check Cache

```bash
python3 -c "
import sys
import os
sys.path.insert(0, 'hooks/scripts')
from complexity_analyzer import ComplexityAnalyzer

analyzer = ComplexityAnalyzer()
import json
print(json.dumps(analyzer.get_cache_stats(), indent=2))
"
```

---

## Getting Help

### Collect Diagnostic Information

```bash
# Create diagnostic report
cat > diagnostic-report.txt << EOF
=== Progress Tracker Diagnostics ===

Date: $(date)
Working Directory: $(pwd)

=== Health Check ===
$(python3 hooks/scripts/progress_manager.py health)

=== Git Status ===
$(git status --short)

=== Progress Status ===
$(python3 hooks/scripts/progress_manager.py status)

=== Progress JSON (first 50 lines) ===
$(head -n 50 .claude/progress.json)

=== Files in .claude ===
$(ls -la .claude/)
EOF

cat diagnostic-report.txt
```

### Report Issues

When reporting issues, include:
1. Diagnostic report (above)
2. Claude Code version
3. Progress Tracker version (from CHANGELOG.md)
4. Steps to reproduce
5. Expected vs actual behavior

---

## Quick Reference

| Issue | Quick Fix |
|-------|-----------|
| No tracking found | `/prog init <name>` |
| Hook timeout | Increase timeout in hooks.json |
| Invalid commit hash | Don't manually edit progress.json |
| Git not clean | `git commit` or `git stash` |
| Corrupted data | Restore from git history |
| Stuck workflow | Clear workflow state |
| Slow performance | Clear cache or split project |
| Superpowers missing | Use fallback workflow |
