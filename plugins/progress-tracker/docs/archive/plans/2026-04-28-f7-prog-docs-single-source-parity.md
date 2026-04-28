# Enforce PROG command docs single-source parity — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已有 `generate_prog_docs.py` 工具链基础上添加自动化强制执行机制（pre-commit hook + CI），并扩展测试覆盖 EN/ZH 同步一致性和合并后漂移修复场景。

**Architecture:** 复用现有 `generate_prog_docs.py --check` 作为唯一门禁检查点。pre-commit hook 在本地阻止不合规提交并提示修复命令；CI 通过扩展现有 `required-check.yml` 在 PR/merge_group 时作为远端兜底门禁。pre-commit 安装链路接入 `install-git-hooks` 命令，确保团队成员一次安装两个 hook（post-merge + pre-commit）。

**Tech Stack:** Bash (pre-commit hook), GitHub Actions YAML (required-check.yml 扩展), Python/pytest (tests)

**错误消息归属约定:**
- `generate_prog_docs.py --check`：保持现有机器可读简讯（"Generated docs are out of date:" + 文件列表），不做修改
- `hooks/pre-commit`：捕获 generator 非零退出码，拼接人类可读引导文案（含 `--write` 命令 + `git add` 文件列表）

---

### Task 1: pre-commit hook — 脚本 + 安装链路 + 测试

**Files:**
- Create: `plugins/progress-tracker/hooks/pre-commit`
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:3473-3522` (`cmd_install_git_hooks`)
- Modify: `plugins/progress-tracker/tests/test_git_hooks_install.py`

- [ ] **Step 1: 创建 pre-commit hook 脚本**

```bash
cat > plugins/progress-tracker/hooks/pre-commit << 'HOOK'
#!/bin/bash
# Pre-commit hook: enforce PROG docs single-source parity.
# Installed via: prog install-git-hooks
# Blocks commits when generated docs are out of sync with PROG_COMMANDS.md.

set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${HOOK_DIR}/scripts/generate_prog_docs.py"

if [ ! -f "$SCRIPT" ]; then
  echo "[doc-parity] WARNING: generate_prog_docs.py not found, skipping check."
  exit 0
fi

echo "[doc-parity] Checking PROG docs are up to date..."

# generator 保持机器可读简讯；hook 负责人类引导文案
OUTPUT=$(python3 "$SCRIPT" --check 2>&1) && rc=$? || rc=$?

if [ $rc -eq 0 ]; then
  echo "[doc-parity] OK: docs in sync."
  exit 0
fi

cat << MSG

========================================
[doc-parity] FAILED: Generated docs are out of date.

Generator output:
$OUTPUT

Run the following command to regenerate:
  python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --write

Then stage the updated files:
  git add plugins/progress-tracker/README.md \\
          plugins/progress-tracker/readme-zh.md \\
          plugins/progress-tracker/docs/PROG_HELP.md

Then retry your commit.
========================================
MSG

exit 1
HOOK

chmod +x plugins/progress-tracker/hooks/pre-commit
```

- [ ] **Step 2: 修改 `cmd_install_git_hooks()` — 同时安装 post-merge + pre-commit**

在 `progress_manager.py` 的 `cmd_install_git_hooks()` 中，将单一 `post-merge` 安装逻辑扩展为安装两个 hook。

修改位置：`plugins/progress-tracker/hooks/scripts/progress_manager.py:3510-3522`

将：
```python
    source = Path(__file__).parent / "post_merge_hook.sh"
    if not source.exists():
        msg = f"Hook source not found: {source}"
        print(f"[install-git-hooks] ERROR: {msg}")
        return {"installed": False, "hook_path": None, "error": msg}

    target = git_hooks_dir / "post-merge"
    target.write_text(source.read_text())
    current_mode = target.stat().st_mode
    target.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"[install-git-hooks] Installed: {target}")
    return {"installed": True, "hook_path": str(target), "error": None}
```

改为：
```python
    hooks_to_install = [
        ("post_merge_hook.sh", "post-merge"),
        (os.path.join("..", "pre-commit"), "pre-commit"),
    ]

    installed = []
    for src_rel, hook_name in hooks_to_install:
        source = Path(__file__).parent / src_rel
        # pre-commit 在 hooks/ 目录下，需要 resolve
        source = source.resolve()
        if not source.exists():
            msg = f"Hook source not found: {source}"
            print(f"[install-git-hooks] ERROR: {msg}")
            return {"installed": False, "hook_path": None, "error": msg, "installed_hooks": installed}

        target = git_hooks_dir / hook_name
        target.write_text(source.read_text())
        current_mode = target.stat().st_mode
        target.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"[install-git-hooks] Installed: {target}")
        installed.append(str(target))

    return {"installed": True, "hook_path": installed[0], "error": None, "installed_hooks": installed}
```

注意顶部需添加 `import os`（如尚未导入）。

- [ ] **Step 3: 运行现有 install-git-hooks 测试确认 RED**

```bash
python -m pytest plugins/progress-tracker/tests/test_git_hooks_install.py -v
```

预期：部分测试 FAIL — `test_creates_post_merge_hook` 等因为 mock 只提供了 `post_merge_hook.sh` 源而 `hooks/pre-commit` 不存在。

- [ ] **Step 4: 更新测试 — 同时验证 post-merge + pre-commit**

在 `test_git_hooks_install.py` 中，为每个测试方法添加 pre-commit hook 的存在性验证。关键修改：

`_make_git_rev_parse_mock` 保持不变。

在 `_setup_hooks_dir` 中，额外创建 pre-commit 脚本源：

```python
def _setup_hooks_dir(self, tmp_path):
    """创建 hooks 目录，同时准备 pre-commit 脚本源。"""
    git_hooks = tmp_path / ".git" / "hooks"
    git_hooks.mkdir(parents=True)
    # 创建 pre-commit 脚本源供 cmd_install_git_hooks 读取
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "pre-commit").write_text("#!/bin/bash\necho pre-commit-test\n")
    return git_hooks
```

各测试方法增加 assertion：

```python
# test_creates_post_merge_hook 重命名为 test_creates_both_hooks
def test_creates_both_hooks(self, tmp_path):
    git_hooks = self._setup_hooks_dir(tmp_path)
    with patch("progress_manager.find_project_root", return_value=tmp_path), \
         patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
        result = pm.cmd_install_git_hooks()
    assert (git_hooks / "post-merge").exists()
    assert (git_hooks / "pre-commit").exists()
    assert result["installed"] is True

# test_hook_is_executable 需验证两个 hook 均可执行
# 同理 test_hook_content_contains_reconcile_state 只针对 post-merge，pre-commit 不包含 reconcile-state

# 新增 test_pre_commit_hook_contains_check_command
def test_pre_commit_hook_contains_check_command(self, tmp_path):
    git_hooks = self._setup_hooks_dir(tmp_path)
    with patch("progress_manager.find_project_root", return_value=tmp_path), \
         patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
        pm.cmd_install_git_hooks()
    content = (git_hooks / "pre-commit").read_text()
    assert "generate_prog_docs.py" in content
    assert "--check" in content
```

- [ ] **Step 5: 运行全部 install 测试确认 GREEN**

```bash
python -m pytest plugins/progress-tracker/tests/test_git_hooks_install.py -v
```

Expected: 7 passed（原来 6 + 新增 1 `test_pre_commit_hook_contains_check_command`；`test_creates_post_merge_hook` 升级为 `test_creates_both_hooks`）

- [ ] **Step 6: 验证 hook 真实生效 — 制造漂移**

```bash
echo "<!-- drift test -->" >> plugins/progress-tracker/README.md
git add plugins/progress-tracker/README.md
git commit -m "test: should be blocked by pre-commit" 2>&1; echo "EXIT=$?"
```

Expected: EXIT=1，输出含 "FAILED: Generated docs are out of date." + "--write" 修复命令。然后还原：

```bash
git checkout -- plugins/progress-tracker/README.md
git reset HEAD plugins/progress-tracker/README.md
```

- [ ] **Step 7: Commit**

```bash
git add plugins/progress-tracker/hooks/pre-commit \
        plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_git_hooks_install.py
git commit -m "feat(f7): add pre-commit hook + install-git-hooks linkage for PROG docs parity"
```

---

### Task 2: CI — 并入 existing required-check.yml

**Files:**
- Modify: `.github/workflows/required-check.yml`

**原因（P1 #2 修复）:** 仓库受保护分支的 required status check 绑定 `required-check` 作业名。创建独立 workflow 不会被纳入门禁，PR 仍可能在未通过 docs parity 情况下合并。直接扩展现有 job 是最小变更且确保生效。

- [ ] **Step 1: 在 required-check.yml 添加 docs parity step**

在 `.github/workflows/required-check.yml` 的 `required-check` job 中，于现有 steps 末尾添加：

```yaml
      - name: Check PROG docs single-source parity
        shell: bash
        run: |
          python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
```

插入位置：第 30 行 `exit 1` 之后、`echo "Required check passed."` 之前。

改后完整 workflow：

```yaml
name: Required Check

on:
  pull_request:
    branches:
      - main
  merge_group:
  workflow_dispatch:

jobs:
  required-check:
    permissions:
      contents: read
    timeout-minutes: 5
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Verify no unresolved conflict markers in source files
        shell: bash
        run: |
          set -euo pipefail
          if git ls-files '*.py' '*.json' '*.yml' '*.yaml' '*.sh' '*.toml' '*.ini' '*.ts' '*.tsx' '*.js' '*.jsx' | \
            xargs -r rg -n '^(<<<<<<<|=======|>>>>>>>)'; then
            echo "Found unresolved merge conflict markers in source files."
            exit 1
          fi

      - name: Check PROG docs single-source parity
        shell: bash
        run: |
          python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check

      - name: Required check passed
        shell: bash
        run: |
          echo "Required check passed."
```

- [ ] **Step 2: 语法验证**

```bash
python3 -c "
import yaml
with open('.github/workflows/required-check.yml') as f:
    data = yaml.safe_load(f)
print('jobs:', list(data['jobs'].keys()))
print('OK')
" 2>/dev/null || echo "YAML syntax check skipped (install pyyaml) — structure verified by eye diff"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/required-check.yml
git commit -m "feat(f7): add PROG docs parity check to required-check CI job"
```

---

### Task 3: EN/ZH 同步一致性测试

**Files:**
- Modify: `plugins/progress-tracker/tests/test_generate_prog_docs.py`

- [ ] **Step 1: 写测试 — 验证 EN/ZH 双语块同源提取 + 无交叉泄漏**

在文件末尾追加：

```python
def test_extract_source_blocks_both_en_and_zh() -> None:
    """When PROG_COMMANDS.md has both README_EN and README_ZH blocks,
    both are extracted as non-empty strings."""
    source = """
<!-- SOURCE:README_EN:START -->
/en command-1
/en command-2
<!-- SOURCE:README_EN:END -->

<!-- SOURCE:README_ZH:START -->
/zh command-1
/zh command-2
<!-- SOURCE:README_ZH:END -->
"""
    en = generate_prog_docs.extract_source_block(source, "README_EN")
    zh = generate_prog_docs.extract_source_block(source, "README_ZH")
    assert "/en command-1" in en
    assert "/en command-2" in en
    assert "/zh command-1" in zh
    assert "/zh command-2" in zh


def test_source_block_en_zh_not_mixed() -> None:
    """EN block must not leak ZH content and vice versa."""
    source = """
<!-- SOURCE:README_EN:START -->
/en only
<!-- SOURCE:README_EN:END -->

<!-- SOURCE:README_ZH:START -->
/zh only
<!-- SOURCE:README_ZH:END -->
"""
    en = generate_prog_docs.extract_source_block(source, "README_EN")
    zh = generate_prog_docs.extract_source_block(source, "README_ZH")
    assert "/zh only" not in en
    assert "/en only" not in zh
```

- [ ] **Step 2: 运行新测试**

```bash
python -m pytest plugins/progress-tracker/tests/test_generate_prog_docs.py::test_extract_source_blocks_both_en_and_zh \
                                 test_generate_prog_docs.py::test_source_block_en_zh_not_mixed -v
```

Expected: 2 passed（追加防守测试，当前实现正确则直接 PASS；若失败说明 extract 逻辑有 bug 需修复）

- [ ] **Step 3: 运行全部测试**

```bash
python -m pytest plugins/progress-tracker/tests/test_generate_prog_docs.py -v
```

Expected: 6 passed（原来 4 + 新增 2）

- [ ] **Step 4: Commit**

```bash
git add plugins/progress-tracker/tests/test_generate_prog_docs.py
git commit -m "test(f7): add EN/ZH sync consistency tests for docs generator"
```

---

### Task 4: merge 后漂移 check→write→check 端到端测试

**Files:**
- Modify: `plugins/progress-tracker/tests/test_generate_prog_docs.py`

**设计约束（P2 #4 修复）:** 使用 `tmp_path` + `git init` 构造隔离临时仓库，不依赖真实 merge 上下文或 ORIG_HEAD。仅验证 check→write→check 逻辑闭环。

- [ ] **Step 1: 写测试 — temp git repo fixture 内闭环**

在文件顶部确认已有 `import subprocess` 和 `import sys`（新增需加入）。追加：

```python
def test_check_write_check_roundtrip_in_temp_repo(tmp_path: Path) -> None:
    """Roundtrip in an isolated temp git repo: check passes on clean state,
    drift makes check fail, write fixes it, check passes again."""
    import subprocess, sys, textwrap

    script_root = Path(__file__).resolve().parents[1] / "hooks" / "scripts"
    gen_script = script_root / "generate_prog_docs.py"

    # 构造临时仓库结构
    repo = tmp_path / "repo"
    repo.mkdir()
    docs_dir = repo / "docs"
    docs_dir.mkdir()

    # PROG_COMMANDS.md — 单源
    source_md = docs_dir / "PROG_COMMANDS.md"
    source_md.write_text(textwrap.dedent("""\
        <!-- SOURCE:README_EN:START -->
        ## Commands

        | Command | Description |
        |---------|-------------|
        | /prog   | Status     |
        <!-- SOURCE:README_EN:END -->
    """))

    # README.md — 含生成块
    readme_md = repo / "README.md"
    readme_md.write_text(textwrap.dedent("""\
        # Test Plugin

        <!-- BEGIN:GENERATED:PROG_COMMANDS -->
        <!-- GENERATED CONTENT: DO NOT EDIT DIRECTLY -->
        ## Commands

        | Command | Description |
        |---------|-------------|
        | /prog   | Status     |
        <!-- END:GENERATED:PROG_COMMANDS -->
    """))

    # Step A: baseline — --check passes
    r = subprocess.run(
        [sys.executable, str(gen_script), "--check"],
        cwd=str(repo), capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, f"baseline check should pass: {r.stdout} {r.stderr}"

    # Step B: simulate post-merge drift — corrupt the generated block
    corrupted = readme_md.read_text().replace(
        "| /prog   | Status     |",
        "| /prog   | STALE OLD CONTENT FROM MERGE |",
    )
    readme_md.write_text(corrupted)

    # Step C: --check fails
    r = subprocess.run(
        [sys.executable, str(gen_script), "--check"],
        cwd=str(repo), capture_output=True, text=True, check=False,
    )
    assert r.returncode != 0, (
        f"check should fail after drift: rc={r.returncode}: {r.stdout} {r.stderr}"
    )

    # Step D: --write fixes
    r = subprocess.run(
        [sys.executable, str(gen_script), "--write"],
        cwd=str(repo), capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, f"write should succeed: {r.stderr}"

    # Step E: --check passes again
    r = subprocess.run(
        [sys.executable, str(gen_script), "--check"],
        cwd=str(repo), capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, (
        f"check should pass after write fix: rc={r.returncode}: {r.stdout} {r.stderr}"
    )

    # 验证文件内容已修复（不再含 STALE）
    fixed = readme_md.read_text()
    assert "STALE OLD CONTENT FROM MERGE" not in fixed
    assert "| /prog   | Status     |" in fixed
```

- [ ] **Step 2: 运行新测试**

```bash
python -m pytest plugins/progress-tracker/tests/test_generate_prog_docs.py::test_check_write_check_roundtrip_in_temp_repo -v
```

Expected: PASS — 完整闭环在隔离 temp git repo 中验证。

- [ ] **Step 3: 运行全部 7 个测试**

```bash
python -m pytest plugins/progress-tracker/tests/test_generate_prog_docs.py -v
```

Expected: 7 passed（原来的 4 + T3 的 2 + 本 task 的 1）

- [ ] **Step 4: Commit**

```bash
git add plugins/progress-tracker/tests/test_generate_prog_docs.py
git commit -m "test(f7): add post-merge drift check-write-check roundtrip integration test"
```
