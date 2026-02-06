# Conventional Commits Reference

## Specification

Conventional commits follow this format:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

## Types

| Type | Description | Example |
|------|-------------|---------|
| `feat` | New feature | `feat: add user authentication` |
| `fix` | Bug fix | `fix: resolve login timeout` |
| `docs` | Documentation only | `docs: update API reference` |
| `style` | Code style changes (formatting, etc.) | `style: format code with black` |
| `refactor` | Code refactoring | `refactor: simplify auth flow` |
| `perf` | Performance improvements | `perf: optimize database queries` |
| `test` | Adding or updating tests | `test: add integration tests` |
| `build` | Build system or dependencies | `build: upgrade to webpack 5` |
| `ci` | CI/CD changes | `ci: add GitHub Actions workflow` |
| `chore` | Other changes (maintenance, etc.) | `chore: update dependencies` |
| `revert` | Revert a previous commit | `revert: feat: add new feature` |

## Scope

Optional scope in parentheses:
- `feat(auth):` - Authentication related
- `fix(api):` - API related
- `fix(BUG-123):` - Specific bug ID

## Description

- Use imperative, present tense: "add" not "added" or "adds"
- Use lowercase: "add feature" not "Add Feature"
- Don't end with a period
- Keep under 72 characters

## Body

- Explain **what** and **why** (not **how**)
- Use imperative mood
- Wrap at 72 characters

## Footer

- **Breaking changes**: Start with `BREAKING CHANGE: `
- **Closes**: `Closes #123`
- **Co-authored**: `Co-Authored-By: Name <email>`

## Examples

### Simple Feature
```
feat: add user profile page
```

### Feature with Body
```
feat: add user authentication

Implement OAuth2 login with Google and GitHub.
Users can now sign in with existing accounts.
```

### Bug Fix with Scope
```
fix(auth): resolve session timeout

Session was expiring after 5 minutes instead of
the configured 30 minutes.
```

### Bug Fix with ID
```
fix(BUG-001): rate calculation overflow

Large numbers caused integer overflow in rate
calculation, resulting in incorrect billing.
```

### Feature with Breaking Change
```
feat: upgrade to API v2

BREAKING CHANGE: API endpoints have changed.
Update integrations to use new endpoints.
```

### Complete Example
```
feat(auth): implement JWT token refresh

Add automatic token refresh mechanism to improve
user experience. Tokens refresh automatically 5
minutes before expiration.

- Add refresh endpoint
- Update token validation logic
- Add refresh token storage

Closes #123
Co-Authored-By: Claude <noreply@anthropic.com>
```

## Progress Tracker Specific Patterns

For the progress-tracker plugin, use these patterns:

### Completed Feature
```
feat: complete <feature name>

Optional details about the implementation.

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Bug Fix
```
fix: <bug description>

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Bug Fix with ID
```
fix(BUG-XXX): <bug description>

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Tools

### Commitlint
Validate commits with commitlint:
```bash
npm install -D @commitlint/cli @commitlint/config-conventional
echo "module.exports = {extends: ['@commitlint/config-conventional']}" > commitlint.config.js
```

### Commitizen
Interactive commit prompt:
```bash
npm install -D commitizen cz-conventional-changelog
echo '{"path": "cz-conventional-changelog"}' > .czrc
npx cz
```

## Resources

- [Conventional Commits](https://www.conventionalcommits.org/)
- [Conventional Changelog](https://github.com/conventional-changelog/conventional-changelog)
- [Angular Commit Convention](https://github.com/angular/angular/blob/master/CONTRIBUTING.md#commit)
