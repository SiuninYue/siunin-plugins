# Repo Policy Probe

Probe repository policy before selecting direct-main vs PR.

## Probe Order

1. `gh api` branch/ruleset metadata.
2. Local policy files (ruleset JSON).
3. Session evidence (`GH006` push rejection).
4. Conservative fallback.

## Output Contract

- `Repo Policy: <protected_pr_required|protected_unknown_rules|unprotected|unknown_conservative>`
- `Repo Policy Evidence: <gh-api|local-config|push-error-gh006|conservative-default>`

## Local File Hints

- `.github/rules/main.json`
- `.github/rulesets/main.json`
- `docs/github-rules/main.json`
- `docs/rules/main.json`
