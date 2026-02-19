# Project Agent Rules

## GH Command Execution (Codex App)

- In this repository, any command starting with `gh` must run with escalated permissions by default.
- Do not attempt `gh` commands in sandbox first.
- Reason: sandbox sessions may fail to access the macOS keychain token, even when host `gh auth` is valid.

## Git Transport Policy

- Use SSH for Git remotes in this repository.
- Keep `origin` as `git@github.com:SiuninYue/siunin-plugins.git` for both fetch and push.
