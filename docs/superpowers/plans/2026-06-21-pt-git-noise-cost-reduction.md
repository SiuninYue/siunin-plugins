# Progress-Tracker Git 噪音与成本削减 Implementation Plan (v3 — EXECUTED)

> **执行状态(已落地在 main):** 前置清理 `dd31ddc`(progress.md 废弃,55 文件/-2900)→ Task 1 `f252049`(砍 set_current 激活 state-sync)→ Task 2 `7ab4653`(白名单单源化 re-export + 派生物/锁/archive 镜像移出跟踪,pathspec 用 `:(glob)` 修正以覆盖根级)→ Task 3 `e867e40`(三份规则文件)。每个 commit 均过 pre-commit 边界检查。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **v2 changelog (纳入 Gemini + Codex 审查):** 修正 `STATE_FILE_NAMES` 重复常量(改为单源 re-export)、删除危险的 `git add -u`、移除自相矛盾的 test_reports gitignore、修正验证步骤、log 命令加 `--max-count`、补强 progress_archive 派生镜像、澄清 "feature start" 措辞。`workspace_entropy` 逻辑改动经核查为 scope creep,列入 Out of Scope 并附理由。

**Goal:** 削减 progress-tracker 在 git 主线制造的自动 commit 噪音,并把"提交规范 + 看 log 过滤"固化进 agent 规则——全部用零模型、纯减法的确定性手段。

**Architecture:** 三处独立改动。(1) 删掉 `set_current`(`/prog-next` 内部激活阶段)多余的 state-sync 提交;(2) 把 state 白名单单源化到 `git_utils`,从中移除派生物,并把派生/运行态文件移出 git 跟踪;(3) 在三份 agent 规则文件钉 commit 模板和 log 过滤命令。**不**引入 hook / 专用 agent / 子模型 / 并行。

**Tech Stack:** Python 3, pytest, git, bash, markdown。

## Global Constraints

- 任何触碰 `plugins/progress-tracker/**` 或 `AGENTS.md`/`CLAUDE.md`/`GEMINI.md` 的改动,提交前必须跑且通过(fail-closed):
  - `bash scripts/check_pm_boundary.sh`
  - `python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check`
- `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` 三份策略意图一致,且在**同一 commit**内更新。
- pytest 调用(本仓库 `python3 -m pytest` 无模块):`/Users/siunin/.local/share/mise/installs/pipx-pytest/latest/bin/pytest`,工作目录 `plugins/progress-tracker`。
- `hooks/scripts/*.py` 子模块不得 `import progress_manager`(反向依赖禁止)。`progress_manager` → `git_utils` 方向允许(已存在,见 `progress_manager.py:2014`)。
- 全程不新增 hook / agent / 模型调用 / 并行。

## Preconditions(执行前必读)

当前工作树**已有大量未提交改动**:部分是用户手动开始的本 plan 工作(已 `git rm` 了派生物、在 `.gitignore` 加了 `progress.md`),部分是无关的 `M` 改动。

- **派生物会"复活"**:`status_summary.v1.json`/`migration_log.json` 虽被手动删,但仍在白名单 + 未 gitignore,下次 prog 运行会重新生成并提交。Task 2 让删除永久生效。
- **执行第一步**:`git status` 摸清现状。本 plan 每个 commit **只精确 add 指定文件**,绝不用 `git add -u` / `git add -A`(会卷入无关改动)。

---

## File Structure

| 文件 | 职责 | Task |
|---|---|---|
| `plugins/progress-tracker/hooks/scripts/feature_commands.py` | 删除 `set_current` 激活阶段的 state-sync 调用 | 1 |
| `plugins/progress-tracker/tests/test_feature_commands.py` | 反转 start 断言 | 1 |
| `plugins/progress-tracker/tests/test_auto_state_commit.py` | 反转 call-site 断言 + 白名单单源/排除断言 | 1,2 |
| `plugins/progress-tracker/hooks/scripts/git_utils.py` | 白名单真相源,移除派生物 | 2 |
| `plugins/progress-tracker/hooks/scripts/progress_manager.py` | 删除重复定义,改为 re-export | 2 |
| `.gitignore` | 忽略派生/运行态 state 文件 + archive 派生镜像 | 2 |
| `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` | commit 模板 + log 过滤命令 | 3 |

---

## Task 1: 删除 `set_current` 激活阶段的冗余 state-sync 提交

**理由:** 一个 feature 周期产生 4 个 `chore(PT)` commit,其中激活时 state 几乎为空、信息价值最低。注意:`/prog-start` 命令早已移除(`architecture.md:670` 确认 `/prog-next` 是唯一入口);这里砍的是 `set_current`(由 `/prog-next` 内部调用)在 `feature_commands.py:110` 的 `auto_state_commit_fn(..., "start")` 调用,**不是**恢复任何命令。`done`/`fix` 的提交保留。

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/feature_commands.py:110`
- Test: `plugins/progress-tracker/tests/test_feature_commands.py:136`(函数 `test_set_current_success`,起 line 98)
- Test: `plugins/progress-tracker/tests/test_auto_state_commit.py:409-418`(`TestCallSiteSetCurrent`)

**Interfaces:**
- Consumes: `FeatureCommandsServices.auto_state_commit_fn`(签名 `Callable[[str, str], Optional[str]]`,不变,仅 `set_current` 不再调用)
- Produces: `set_current` 不再在激活时触发 state commit;`done`(`completion_flow.py:1177`)与 `fix`(`bug_tracker.py:337`)不受影响。

- [ ] **Step 1: 改测试,断言 start 不再触发(先红)**

`tests/test_feature_commands.py` 第 135-136 行,把:
```python
    # Auto commit + parent notification.
    svc.auto_state_commit_fn.assert_called_once_with("F1", "start")
```
改为:
```python
    # Activation no longer auto-commits state (noise reduction); parent notification stays.
    svc.auto_state_commit_fn.assert_not_called()
```

`tests/test_auto_state_commit.py` 的 `TestCallSiteSetCurrent` 类(line 409-418)整体改为:
```python
class TestCallSiteSetCurrent:
    def test_set_current_does_not_auto_commit(self, mock_git_repo):
        assert progress_manager.configure_project_scope(str(mock_git_repo)) is True
        progress_manager.init_tracking("Test", force=True)
        progress_manager.add_feature("Feature 1", ["step 1"])

        with patch.object(progress_manager, "_auto_state_commit") as mock_asc:
            progress_manager.set_current(1)

        mock_asc.assert_not_called()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd plugins/progress-tracker
PYTEST=/Users/siunin/.local/share/mise/installs/pipx-pytest/latest/bin/pytest
"$PYTEST" tests/test_feature_commands.py::test_set_current_success \
  "tests/test_auto_state_commit.py::TestCallSiteSetCurrent::test_set_current_does_not_auto_commit" -q
```
Expected: FAIL（代码仍调用 `auto_state_commit_fn(..., "start")`）

- [ ] **Step 3: 删除激活处的 state-sync 调用**

`hooks/scripts/feature_commands.py` 第 108-114 行,把:
```python
    svc.save_progress_md_fn("")

    svc.auto_state_commit_fn(f"F{feature_id}", "start")

    # Notify parent tracker to upsert active_routes for this child feature.
```
改为:
```python
    svc.save_progress_md_fn("")

    # Notify parent tracker to upsert active_routes for this child feature.
```

- [ ] **Step 4: 跑测试确认通过**

```bash
"$PYTEST" tests/test_feature_commands.py::test_set_current_success \
  "tests/test_auto_state_commit.py::TestCallSiteSetCurrent::test_set_current_does_not_auto_commit" -q
```
Expected: 2 passed

- [ ] **Step 5: 两个测试文件全量回归**

```bash
"$PYTEST" tests/test_feature_commands.py tests/test_auto_state_commit.py -q
```
Expected: all passed（`cmd_done` 的 `assert_called_once_with(..., "done")` 仍通过——done 未动）

- [ ] **Step 6: 边界检查**

```bash
cd /Users/siunin/Projects/Claude-Plugins
bash scripts/check_pm_boundary.sh && python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
```
Expected: 均 PASS

- [ ] **Step 7: Commit（精确 add）**

```bash
git add plugins/progress-tracker/hooks/scripts/feature_commands.py \
        plugins/progress-tracker/tests/test_feature_commands.py \
        plugins/progress-tracker/tests/test_auto_state_commit.py
git commit -m "refactor(progress-tracker): drop redundant state-sync commit on feature activation"
```

---

## Task 2: 白名单单源化 + 派生/运行态文件移出 git 跟踪

**理由:** (a) `STATE_FILE_NAMES`/`STATE_DIR_NAMES` 在 `git_utils.py:35` 和 `progress_manager.py:236` **重复定义**(F18 模块化残留),易 drift——单源到 `git_utils`,`progress_manager` re-export(实测 `git_utils` 可独立 import,无循环)。(b) 白名单含派生物 `status_summary.v1.json`(可重建,`admin_ops.py:161`)和运行日志 `migration_log.json`,移除后 state sync 只提交真正的源。(c) `progress.lock`(运行锁)误被跟踪;archive 里 `*.progress.md`/`*.status-summary.v1.json` 是派生镜像。

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/git_utils.py:35-44`(白名单真相源)
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py:235-249`(删重复,改 re-export)
- Modify: `plugins/progress-tracker/tests/test_auto_state_commit.py`(`TestStateFileConstants` 加断言)
- Modify: `.gitignore`
- git index: `git rm --cached` 派生/锁/archive 镜像

**Interfaces:**
- Consumes: `git_utils.STATE_FILE_NAMES`(`_get_dirty_state_files` 遍历它决定提交哪些文件)
- Produces: `git_utils.STATE_FILE_NAMES` 移除 `status_summary.v1.json`/`migration_log.json`;`progress_manager.STATE_FILE_NAMES is git_utils.STATE_FILE_NAMES`(同一对象)。**保留**:`progress.json`、`checkpoints.json`、`progress_history.json`、`sprint_ledger.jsonl`、`audit.log`、`project_memory.json`。`STATE_DIR_NAMES`(含 `test_reports`/`progress_archive`)**不动**。

- [ ] **Step 1: 改 `TestStateFileConstants`,加单源 + 排除断言(先红)**

`tests/test_auto_state_commit.py` 的 `TestStateFileConstants` 类(line 17-33),在末尾(`test_state_dir_names_contains_required_dirs` 之后)追加:
```python
    def test_state_file_names_excludes_derived_projections(self):
        assert "status_summary.v1.json" not in progress_manager.STATE_FILE_NAMES
        assert "migration_log.json" not in progress_manager.STATE_FILE_NAMES

    def test_whitelist_single_sourced_from_git_utils(self):
        import git_utils
        assert progress_manager.STATE_FILE_NAMES is git_utils.STATE_FILE_NAMES
        assert progress_manager.STATE_DIR_NAMES is git_utils.STATE_DIR_NAMES
```
现有断言(`contains_required` / `excludes progress.md` / `excludes lock` / `dir contains test_reports,progress_archive`)**保持不变**——它们在改动后仍应成立。

- [ ] **Step 2: 跑测试确认失败**

```bash
cd plugins/progress-tracker
PYTEST=/Users/siunin/.local/share/mise/installs/pipx-pytest/latest/bin/pytest
"$PYTEST" tests/test_auto_state_commit.py::TestStateFileConstants -q
```
Expected: `test_state_file_names_excludes_derived_projections` 与 `test_whitelist_single_sourced_from_git_utils` FAIL

- [ ] **Step 3: 从 `git_utils` 白名单移除派生物（真相源）**

`hooks/scripts/git_utils.py` 第 35-44 行,把:
```python
STATE_FILE_NAMES = [
    PROGRESS_JSON,
    CHECKPOINTS_JSON,
    PROGRESS_HISTORY_JSON,
    "sprint_ledger.jsonl",
    "status_summary.v1.json",
    "audit.log",
    "project_memory.json",
    "migration_log.json",
]
```
改为:
```python
# Single source of truth for auto-commit whitelist (progress_manager re-exports this).
# Derived projection (status_summary.v1.json) and runtime log (migration_log.json) are
# rebuilt locally and intentionally excluded to keep main-line history low-noise.
STATE_FILE_NAMES = [
    PROGRESS_JSON,
    CHECKPOINTS_JSON,
    PROGRESS_HISTORY_JSON,
    "sprint_ledger.jsonl",
    "audit.log",
    "project_memory.json",
]
```

- [ ] **Step 4: `progress_manager` 删除重复定义,改为 re-export**

`hooks/scripts/progress_manager.py` 第 235-249 行,把:
```python
# State files managed by progress-tracker (whitelist for auto-commit)
STATE_FILE_NAMES = [
    PROGRESS_JSON,
    CHECKPOINTS_JSON,
    PROGRESS_HISTORY_JSON,
    "sprint_ledger.jsonl",
    "status_summary.v1.json",
    "audit.log",
    "project_memory.json",
    "migration_log.json",
]
STATE_DIR_NAMES = [
    "test_reports",
    "progress_archive",
]
```
改为:
```python
# State file/dir whitelists are single-sourced in git_utils to prevent drift
# (auto-commit logic reads git_utils.STATE_FILE_NAMES via _get_dirty_state_files).
from git_utils import STATE_FILE_NAMES, STATE_DIR_NAMES  # noqa: E402,F401
```
(标量常量 `PROGRESS_JSON`/`CHECKPOINTS_JSON`/`PROGRESS_HISTORY_JSON` 的定义/import 保持不动——它们在别处仍被使用,如 `progress_manager.py:1715`。)

- [ ] **Step 5: 跑测试确认通过**

```bash
"$PYTEST" tests/test_auto_state_commit.py -q
```
Expected: all passed（既有 `_get_dirty_state_files`/audit.log 测试不依赖被移除的两项）

- [ ] **Step 6: 更新 `.gitignore`**

仓库根 `.gitignore`,在 line 162(`**/docs/progress-tracker/state/progress.md`)下方追加（**不含 test_reports**——它仍由 `STATE_DIR_NAMES` 管理,gitignore 它会与代码矛盾）:
```gitignore
# progress-tracker derived projection + runtime artifacts; rebuilt locally, keep local-only.
**/docs/progress-tracker/state/status_summary.v1.json
**/docs/progress-tracker/state/migration_log.json
**/docs/progress-tracker/state/progress.lock
# archived human/projection mirrors; keep only the structured *.progress.json source.
**/docs/progress-tracker/state/progress_archive/*.progress.md
**/docs/progress-tracker/state/progress_archive/*.status-summary.v1.json
```

- [ ] **Step 7: 从 git index 移除这些文件的所有实例（保留本地，不用 `git add -u`）**

```bash
cd /Users/siunin/Projects/Claude-Plugins
git ls-files '*/docs/progress-tracker/state/status_summary.v1.json' \
             '*/docs/progress-tracker/state/migration_log.json' \
             '*/docs/progress-tracker/state/progress.lock' \
             '*/docs/progress-tracker/state/progress_archive/*.progress.md' \
             '*/docs/progress-tracker/state/progress_archive/*.status-summary.v1.json' \
  | xargs -r git rm --cached
```
Expected: 列出并取消跟踪上述实例（本地文件保留;`git rm --cached` 已 stage 这些删除）

- [ ] **Step 8: 验证忽略生效（用 ls-files / check-ignore,不用 `git status | grep`）**

```bash
# (a) 应为空——已不再跟踪:
git ls-files '*/docs/progress-tracker/state/status_summary.v1.json' \
             '*/docs/progress-tracker/state/progress.lock' \
             '*/docs/progress-tracker/state/migration_log.json'
# (b) 应命中——已被忽略:
git check-ignore -v plugins/progress-tracker/docs/progress-tracker/state/progress.lock
# (c) 源仍在跟踪——应有输出:
git ls-files '*/docs/progress-tracker/state/progress_archive/*.progress.json' | head -1
```
Expected: (a) 无输出;(b) 打印 .gitignore 规则;(c) 有 `.progress.json` 实例

- [ ] **Step 9: 冒烟验证 summary 缺失可重建**

```bash
cd plugins/progress-tracker
"$PYTEST" tests/ -q -k "status_summary or summary_proj or admin" 2>&1 | tail -8
```
Expected: 相关测试通过,确认 summary 缺失由 projector 重建,无 crash

- [ ] **Step 10: 边界检查**

```bash
cd /Users/siunin/Projects/Claude-Plugins
bash scripts/check_pm_boundary.sh && python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
```
Expected: 均 PASS

- [ ] **Step 11: Commit（精确 add + 人工核对，禁用 `git add -u`）**

```bash
git add .gitignore \
        plugins/progress-tracker/hooks/scripts/git_utils.py \
        plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_auto_state_commit.py
# git rm --cached 已 stage 派生物删除;务必人工核对 staged 内容只含本 task 相关:
git diff --cached --name-status
git commit -m "chore(progress-tracker): single-source state whitelist; stop tracking derived state"
```

---

## Task 3: 规则文件固化 commit 模板与 log 过滤命令

**理由:** 让 AI **一次写对** commit(避免 hook 拦截-重试的 token 往返),并默认用**带 `--max-count` 的过滤命令**看 log(skip 自动 state-sync + 限制长度,双重省成本)。常驻成本仅几行,远低于一次 retry。

**Files:**
- Modify: `AGENTS.md`、`CLAUDE.md`、`GEMINI.md`(三份内容逐字一致,同 commit)

**Interfaces:**
- Consumes: 现有 `## Git/GitHub Conventions` 小节(三份均在 line 13 附近)
- Produces: 三份新增同样两条规则;`check_pm_boundary.sh` 校验三份一致。

- [ ] **Step 1: 三份文件的 `## Git/GitHub Conventions` 小节追加相同内容**

对 `AGENTS.md`、`CLAUDE.md`、`GEMINI.md` 各自,在该小节(`Prefer SSH Git remotes` 之后)追加**逐字相同**:
```markdown
- Manual commits follow Conventional Commits: `type(scope): summary` (types: feat/fix/refactor/chore/docs/test). One logical change per commit. Branch/PR/merge decisions follow the `progress-tracker:git-auto` skill.
- When reviewing history, filter auto state-sync noise and cap length — use:
  `git log --oneline -50 --perl-regexp --invert-grep --grep='state sync'`
  Do not run bare `git log` for review (it floods context with `chore(PT): state sync` commits).
```

- [ ] **Step 2: 验证三份一致 + 边界检查**

```bash
cd /Users/siunin/Projects/Claude-Plugins
diff <(grep -A2 "perl-regexp" AGENTS.md) <(grep -A2 "perl-regexp" CLAUDE.md) && \
diff <(grep -A2 "perl-regexp" CLAUDE.md) <(grep -A2 "perl-regexp" GEMINI.md) && \
echo "THREE FILES CONSISTENT"
bash scripts/check_pm_boundary.sh && python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check
```
Expected: `THREE FILES CONSISTENT` + 检查 PASS

- [ ] **Step 3: 验证过滤命令真能 skip 噪音**

```bash
git log --oneline -50 --perl-regexp --invert-grep --grep='state sync' | grep -c "state sync"
```
Expected: `0`

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md CLAUDE.md GEMINI.md
git commit -m "docs(progress-tracker): add commit-format + log-filter rules to agent guides"
```

---

## Out of Scope（经核查后明确不做）

| 项 | 核查结论 |
|---|---|
| **改 `workspace_entropy.py` 分类逻辑** | Codex 提议让它只对源文件报 auto_commit。核查:`classify_dirty_entries` 只处理出现在 `git status` porcelain 的脏文件;gitignore 后派生物**不再进 porcelain**,运行时不会被归类。`test_workspace_entropy.py:14` 是直接构造输入测**前缀匹配逻辑**,与 git 跟踪状态无关,**不会失败也不破坏功能**。改它是 scope creep。 |
| 合并 done 周期 `sign-off`/`closeout`/`state-sync` | 这些 commit 在 python 中无 f-string——是 git-auto skill 流程里 AI 手写的,合并需改 skill 流程,需独立调研。 |
| 标量常量 `PROGRESS_JSON` 等在两文件重复 | 值为字面量字符串,drift 风险极低;本次只单源化两个 list。 |
| 移除 `test_reports` 跟踪 | 需判断测试报告的审计价值 + 改 `STATE_DIR_NAMES` + 改测试,超出降噪核心范围。 |
| PreToolUse hook 校验 / 换前缀 / filter-repo 重写历史 / pt-state 分支 / 便宜模型·agent·并行 | 前几轮成本核算已否决(陷阱/零收益/与多设备互斥/反而增成本)。 |

## Self-Review

- **Spec coverage:** 减噪音 → Task 1(砍激活提交)+ Task 2(派生物移出 + 白名单瘦身);精准 commit → Task 3(模板);看 log 省成本 → Task 3(过滤 + max-count)。✓
- **审查闭环:** 重复常量 → Task 2 Step 3-4 单源 re-export + Step 1 `is` 断言;`git add -u` → Task 1/2 全改精确 add;test_reports 矛盾 → 不再 gitignore;验证步骤 → Step 8 用 ls-files/check-ignore;log 长度 → Task 3 `-50`;archive 镜像 → Step 6/7 覆盖;措辞 → Task 1 理由澄清。✓
- **Placeholder scan:** 所有步骤含确切路径、行号、代码块、命令与预期输出。✓
- **Type consistency:** `auto_state_commit_fn` 签名不变;`STATE_FILE_NAMES` 经 re-export 为同一对象(`is` 可断言);三份规则文件逐字相同。✓
- **依赖:** Task 1/2/3 互相独立,任意顺序;各以独立 commit 收尾。Task 2 内部 Step 3(git_utils)必须先于 Step 4(re-export),否则 import 的是旧值——但二者在同一 commit,测试在 Step 5 统一验证。

## 预期效果

- 单 feature 周期 `chore(PT)`:4 → 3(砍激活提交;done 周期合并属 Out of Scope)。
- 每次 state sync 提交文件数减少(剔除 2 个高频派生物);锁/archive 镜像不再复活。
- 消除 `STATE_FILE_NAMES` 重复定义这一 drift 隐患。
- AI/人看 log 默认过滤 + 限长,review 上下文不再被 `state sync` 刷屏。
- 运行时零新增模型/hook 成本。
