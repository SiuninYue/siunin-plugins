# F5: Apply Progressive Disclosure Budget to Oversized SKILL Files

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce SKILL.md file sizes across all plugins by extracting long-form examples, templates, and implementation details into `references/`, `examples/`, and `scripts/` subdirectories, maintaining full link integrity.

**Architecture:** Two compliance gates: SOP gate (SKILL.md < 500 lines, hard limit) and repo budget gate (> 250 lines flagged). Extracted content lives in `references/` (patterns, algorithms, detailed specs), `examples/` (full examples, templates, conversations), `scripts/` (automation scripts). Each extracted section gets a ≤8-line summary + relative link in SKILL.md.

**Tech Stack:** Markdown, bash (`wc -l`), pytest for contract regression

---

## File Structure

**New files to create:**
- `plugins/package-manager/skills/package-manager/scripts/update-scripts.md`
- `plugins/progress-tracker/skills/progress-status/examples/status-display-examples.md`
- `plugins/progress-tracker/skills/progress-status/references/special-situations.md`
- `plugins/progress-tracker/skills/architectural-planning/references/planning-templates.md`
- `plugins/progress-tracker/skills/architectural-planning/examples/example-conversation.md`
- `plugins/progress-tracker/skills/bug-fix/` ← append to existing `references/workflow.md` and `references/integration.md`
- `plugins/progress-tracker/skills/feature-breakdown/references/templates.md`
- `plugins/progress-tracker/skills/feature-breakdown/examples/conversations.md`
- `plugins/super-product-manager/skills/launch/references/templates.md`
- `plugins/super-product-manager/skills/launch/examples/launch-example.md`
- `plugins/super-product-manager/skills/roadmap/examples/roadmap-examples.md`
- `plugins/super-product-manager/skills/prd/examples/prd-examples.md`
- `plugins/super-product-manager/skills/prd/references/quick-reference.md`
- `plugins/super-product-manager/skills/prd/references/prd-organization.md`
- `plugins/super-product-manager/skills/user-story/references/card-template.md`
- `plugins/super-product-manager/skills/user-story/examples/user-story-examples.md`

**Files to modify:**
- `plugins/package-manager/skills/package-manager/SKILL.md` (570 → ~433 lines)
- `plugins/progress-tracker/skills/progress-status/SKILL.md` (504 → ~400 lines)
- `plugins/progress-tracker/skills/architectural-planning/SKILL.md` (442 → ~265 lines)
- `plugins/progress-tracker/skills/bug-fix/SKILL.md` (431 → ~330 lines)
- `plugins/progress-tracker/skills/feature-breakdown/SKILL.md` (370 → ~290 lines)
- `plugins/super-product-manager/skills/launch/SKILL.md` (458 → ~270 lines)
- `plugins/super-product-manager/skills/roadmap/SKILL.md` (413 → ~305 lines)
- `plugins/super-product-manager/skills/prd/SKILL.md` (389 → ~276 lines)
- `plugins/super-product-manager/skills/user-story/SKILL.md` (384 → ~220 lines)

---

## Task 1: Baseline Audit

**Files:** No changes — audit only.

- [ ] **Step 1: Run full audit**

```bash
wc -l plugins/*/skills/*/SKILL.md | sort -nr | head -20
```

Expected top violations:
```
570 plugins/package-manager/skills/package-manager/SKILL.md
504 plugins/progress-tracker/skills/progress-status/SKILL.md
458 plugins/super-product-manager/skills/launch/SKILL.md
442 plugins/progress-tracker/skills/architectural-planning/SKILL.md
431 plugins/progress-tracker/skills/bug-fix/SKILL.md
417 plugins/progress-tracker/skills/feature-implement/SKILL.md  ← out of scope (see note)
413 plugins/super-product-manager/skills/roadmap/SKILL.md
```

> **Scope note:** `feature-implement/SKILL.md` (417 lines) exceeds the 250-line repo budget but is **intentionally out of scope for F5**. It has no natural "long examples/templates" block to extract cleanly (all content is active workflow logic). Will be addressed in a follow-up F5b pass.

- [ ] **Step 2: Verify contract tests pass before any changes (baseline)**

```bash
cd /Users/siunin/Projects/Claude-Plugins && pytest -q plugins/progress-tracker/tests/test_command_discovery_contract.py
```

Expected: all PASS (confirms baseline is clean before changes)

---

## Task 2: Fix SOP Violation — package-manager (570 → ~433 lines)

**Files:**
- Modify: `plugins/package-manager/skills/package-manager/SKILL.md:364-509`
- Create: `plugins/package-manager/skills/package-manager/scripts/update-scripts.md`

**What to extract:** The entire `## 快捷脚本` section (SKILL.md lines 364–509, ~145 lines of bash functions `update-all`, `update-global`, `update-project`).

- [ ] **Step 1: Verify the section exists and note line count**

```bash
grep -n "^## 快捷脚本" plugins/package-manager/skills/package-manager/SKILL.md
wc -l plugins/package-manager/skills/package-manager/SKILL.md
```

Expected: line ~364, total 570 lines

- [ ] **Step 2: Create `scripts/update-scripts.md` with the extracted content**

Create `plugins/package-manager/skills/package-manager/scripts/update-scripts.md` containing the full content of the `## 快捷脚本` section (lines 364–509 of SKILL.md). The file should begin with:

```markdown
# 更新脚本（Update Scripts）

将以下函数添加到 `~/.zshrc` 或 `~/.bashrc`：

## update-all

```bash
# === 并发更新所有内容（工具 + 全局包 + 项目依赖）===
# 用法: update-all [--skip-brew] [--skip-mise] [--skip-rust] [--skip-project]
update-all() {
    local skip_mise=false skip_brew=false skip_rust=false skip_project=false

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-brew) skip_brew=true ;;
            --skip-mise) skip_mise=true ;;
            --skip-rust) skip_rust=true ;;
            --skip-project) skip_project=true ;;
            *) echo "❌ 未知参数: $1"; return 1 ;;
        esac
        shift
    done

    echo "🚀 开始并发更新所有包管理器..."
    echo "======================================"

    # 并发更新全局工具
    if ! $skip_mise; then
        echo "🔧 mise 工具更新中..."
        mise upgrade &
    fi

    if ! $skip_brew && command -v brew &>/dev/null; then
        echo "📦 Homebrew 更新中..."
        brew upgrade &>/dev/null &
    fi

    if ! $skip_rust && command -v rustup &>/dev/null; then
        echo "⚙️  Rust 更新中..."
        rustup update &
    fi

    # 等待所有后台任务完成
    wait

    # Homebrew 清理（需要顺序执行）
    if ! $skip_brew && command -v brew &>/dev/null; then
        echo "🧹 清理 Homebrew 缓存..."
        brew cleanup &>/dev/null
    fi

    # 更新全局包
    echo "🌐 更新全局包..."
    mise exec uv -- uv tool upgrade --all 2>/dev/null || true
    mise exec pnpm -- pnpm update -g 2>/dev/null || true
    npm update -g 2>/dev/null || true

    # 更新 Claude Code（使用 latest 通道）
    if ! $skip_brew && command -v brew &>/dev/null; then
        echo "🤖 更新 Claude Code (latest 通道)..."
        brew upgrade --cask claude-code@latest --greedy &>/dev/null || true
    fi

    # 更新项目依赖
    if ! $skip_project; then
        echo "📂 更新项目依赖..."
        [ -f "Cargo.toml" ] && cargo update &>/dev/null
        [ -f "Package.swift" ] && swift package update &>/dev/null
        [ -f "pyproject.toml" ] && mise exec uv -- uv sync --upgrade &>/dev/null
        if [ -f "package.json" ]; then
            [ -f "pnpm-lock.yaml" ] && mise exec pnpm -- pnpm update &>/dev/null
            [ -f "bun.lock" ] && mise exec bun -- bun update &>/dev/null
            [ ! -f "pnpm-lock.yaml" ] && [ ! -f "bun.lock" ] && npm update &>/dev/null
        fi
        [ -f "Gemfile" ] && bundle update &>/dev/null
        [ -f "go.mod" ] && go get -u ./... &>/dev/null && go mod tidy &>/dev/null
    fi

    echo "======================================"
    echo "✅ 检查过时项..."
    mise outdated 2>/dev/null || true
    command -v brew &>/dev/null && brew outdated 2>/dev/null || true
    echo "🎉 全部更新完成！"
}
```

## update-global

```bash
# === 仅更新全局工具 ===
# 用法: update-global [--skip-brew] [--skip-mise] [--skip-rust]
update-global() {
    local skip_mise=false skip_brew=false skip_rust=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-brew) skip_brew=true ;;
            --skip-mise) skip_mise=true ;;
            --skip-rust) skip_rust=true ;;
            *) echo "❌ 未知参数: $1"; return 1 ;;
        esac
        shift
    done

    echo "🚀 开始并发更新全局工具..."

    if ! $skip_mise; then mise upgrade &; fi
    if ! $skip_brew && command -v brew &>/dev/null; then brew upgrade &>/dev/null &; fi
    if ! $skip_rust && command -v rustup &>/dev/null; then rustup update &; fi

    wait

    if ! $skip_brew && command -v brew &>/dev/null; then
        brew cleanup &>/dev/null
    fi

    echo "📦 更新全局包..."
    mise exec uv -- uv tool upgrade --all 2>/dev/null || true
    mise exec pnpm -- pnpm update -g 2>/dev/null || true
    npm update -g 2>/dev/null || true

    # 更新 Claude Code（使用 latest 通道）
    if ! $skip_brew && command -v brew &>/dev/null; then
        echo "🤖 更新 Claude Code (latest 通道)..."
        brew upgrade --cask claude-code@latest --greedy &>/dev/null || true
    fi

    echo "✅ 全局更新完成！"
}
```

## update-project

```bash
# 仅更新当前项目
update-project() {
    if [ -f "Cargo.toml" ]; then cargo update
    elif [ -f "Package.swift" ]; then swift package update
    elif [ -f "pyproject.toml" ]; then mise exec uv -- uv sync --upgrade
    elif [ -f "package.json" ]; then
        [ -f "pnpm-lock.yaml" ] && mise exec pnpm -- pnpm update
        [ -f "bun.lock" ] && mise exec bun -- bun update
        [ ! -f "pnpm-lock.yaml" ] && [ ! -f "bun.lock" ] && npm update
    elif [ -f "Gemfile" ]; then bundle update
    elif [ -f "go.mod" ]; then go get -u ./... && go mod tidy
    else echo "❓ 未检测到支持的项目类型"; fi
}
```

## 使用方法

```bash
update-all      # 更新所有内容
update-global   # 仅更新全局工具
update-project  # 仅更新当前项目
```
```

- [ ] **Step 3: Replace the `## 快捷脚本` section in SKILL.md with a summary link**

In `plugins/package-manager/skills/package-manager/SKILL.md`, replace lines 364–510 (from `## 快捷脚本` through the `### 使用方法` block) with:

```markdown
## 快捷脚本

三个 shell 函数可一键完成更新：

- `update-all` — 并发更新全部（工具 + 全局包 + 项目依赖），支持 `--skip-*` 标志
- `update-global` — 仅更新全局工具（mise + brew + rustup）
- `update-project` — 仅更新当前项目依赖（自动检测 Cargo/Swift/Python/Node/Ruby/Go）

完整函数代码见 [`scripts/update-scripts.md`](scripts/update-scripts.md)。将函数粘贴到 `~/.zshrc` 后即可使用。
```

- [ ] **Step 4: Verify line count reduction**

```bash
wc -l plugins/package-manager/skills/package-manager/SKILL.md
```

Expected: ≤ 435 lines (SOP compliant: < 500)

- [ ] **Step 5: Verify content integrity — scripts file exists and has bash functions**

```bash
wc -l plugins/package-manager/skills/package-manager/scripts/update-scripts.md
grep -c "^update-" plugins/package-manager/skills/package-manager/scripts/update-scripts.md
```

Expected: scripts file ≥ 100 lines, grep returns ≥ 3 matches

- [ ] **Step 6: Commit**

```bash
git add plugins/package-manager/skills/package-manager/SKILL.md \
        plugins/package-manager/skills/package-manager/scripts/update-scripts.md
git commit -m "feat(f5): extract update-scripts from package-manager SKILL.md (SOP compliance)"
```

---

## Task 3: Fix SOP Violation — progress-status (504 → ~400 lines)

**Files:**
- Modify: `plugins/progress-tracker/skills/progress-status/SKILL.md`
- Create: `plugins/progress-tracker/skills/progress-status/examples/status-display-examples.md`
- Create: `plugins/progress-tracker/skills/progress-status/references/special-situations.md`

**What to extract:**
- `## Special Situations` (SKILL.md lines 303–343, ~40 lines) → `references/special-situations.md`
- `## Example Outputs` (SKILL.md lines 356–421, ~65 lines) → `examples/status-display-examples.md`

- [ ] **Step 1: Confirm section boundaries**

```bash
grep -n "^## Special Situations\|^## Integration with Commands\|^## Example Outputs\|^## Key Guidelines" \
  plugins/progress-tracker/skills/progress-status/SKILL.md
```

Expected output (approx):
```
303:## Special Situations
344:## Integration with Commands
356:## Example Outputs
422:## Key Guidelines
```

- [ ] **Step 2: Create `references/special-situations.md`**

Create `plugins/progress-tracker/skills/progress-status/references/special-situations.md` with content copied from SKILL.md lines 303–343:

```markdown
# Special Situations

## Uncommitted Changes

When `git status` shows uncommitted changes:

```markdown
### ⚠️ Uncommitted Changes Detected

You have uncommitted changes. Consider:
- Committing current work with `/prog done` (if feature is complete)
- Stashing changes if switching context
- Reviewing changes before continuing
```

## Stale Tracking (No recent Git activity)

If last commit was more than a day ago:

```markdown
### 💤 Inactive Project

Last Git activity was <time> ago.

Resume by:
- Using `/prog` to review current state
- Running `/prog next` to continue implementation
```

## Feature Without Test Steps

If a feature has empty or missing `test_steps`:

```markdown
### ⚠️ Feature Missing Test Steps

Feature "<name>" lacks clear test steps.

Consider updating test steps before marking complete.
```
```

- [ ] **Step 3: Create `examples/status-display-examples.md`**

Create `plugins/progress-tracker/skills/progress-status/examples/status-display-examples.md` with content copied from SKILL.md lines 356–421 (the `## Example Outputs` section through the Empty State example).

File starts with:
```markdown
# Status Display Examples

## Active Project Example

```markdown
## Project Progress: User Authentication System

**Status**: 2/5 completed (40%)
**Created**: 2024-01-18T10:00:00Z

### In Progress
- [*] Registration API Endpoint
  Test steps:
  - POST /api/register with valid data
  - Verify user record created in database
  - Test validation with invalid email

### Pending (3 remaining)
- [ ] Login API Endpoint
- [ ] JWT Token Generation
- [ ] Password Reset Flow

### Recent Git Activity
```
abc1234 feat: complete user database model
def5678 chore: initialize progress tracking
```

### Next Steps

Current feature is in progress. When ready:
1. Verify the implementation passes test steps
2. Run `/prog done` to test and commit

---
**Paste into a new session to continue:**

/progress-tracker:prog-next

Feature: F3 "Registration API Endpoint" | Phase: execution
Plan: docs/plans/2024-01-18-registration-api.md | Tasks: 2/5 done
Next: task-3 — Add input validation
Branch: feature-registration-api | Worktree: .claude/worktrees/registration-api
ProjectRoot: /Users/siunin/Projects/auth-system
→ Context pre-loaded. Resume from task 3.
---
```

## Empty State Example

```markdown
## No Active Progress Tracking

No project tracking found in the current directory.

Get started:
```
/prog init Build a user authentication system
```

This will:
- Analyze your goal
- Create a feature breakdown
- Initialize progress tracking
```
```

- [ ] **Step 4: Replace sections in SKILL.md with summary links**

In `plugins/progress-tracker/skills/progress-status/SKILL.md`, replace the `## Special Situations` section (lines 303–343) with:

```markdown
## Special Situations

Three common edge cases are handled: uncommitted changes (warn + suggest stash/commit), stale tracking (inactive project notice), feature without test steps (reminder to add steps). See [`references/special-situations.md`](references/special-situations.md) for full response templates.
```

Replace the `## Example Outputs` section (lines 356–421) with:

```markdown
## Example Outputs

See [`examples/status-display-examples.md`](examples/status-display-examples.md) for a full Active Project example and Empty State example showing expected output format.
```

- [ ] **Step 5: Verify line count**

```bash
wc -l plugins/progress-tracker/skills/progress-status/SKILL.md
```

Expected: ≤ 410 lines (SOP compliant: < 500)

- [ ] **Step 6: Run contract tests**

```bash
pytest -q plugins/progress-tracker/tests/test_command_discovery_contract.py
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add plugins/progress-tracker/skills/progress-status/SKILL.md \
        plugins/progress-tracker/skills/progress-status/examples/status-display-examples.md \
        plugins/progress-tracker/skills/progress-status/references/special-situations.md
git commit -m "feat(f5): extract examples+special-situations from progress-status SKILL.md (SOP compliance)"
```

---

## Task 4: SPM launch (458 → ~270 lines)

**Files:**
- Modify: `plugins/super-product-manager/skills/launch/SKILL.md`
- Create: `plugins/super-product-manager/skills/launch/references/templates.md`
- Create: `plugins/super-product-manager/skills/launch/examples/launch-example.md`

**What to extract:**
- `## 上线沟通模板` (lines 171–219, ~48 lines) + `## 上线报告模板` (lines 263–297, ~34 lines) → `references/templates.md`
- `## 示例对话` (lines 300–419, ~119 lines) → `examples/launch-example.md`

- [ ] **Step 1: Confirm section boundaries**

```bash
grep -n "^## 上线沟通模板\|^## 致命问题检查\|^## 上线报告模板\|^## 示例对话\|^## 常见错误对照" \
  plugins/super-product-manager/skills/launch/SKILL.md
```

Expected:
```
171:## 上线沟通模板
221:## 致命问题检查
263:## 上线报告模板
300:## 示例对话
422:## 常见错误对照
```

- [ ] **Step 2: Create `references/templates.md`**

Create `plugins/super-product-manager/skills/launch/references/templates.md` containing:
1. Full `## 上线沟通模板` section content (lines 171–219) — internal announcement template + external user announcement template
2. Full `## 上线报告模板` section content (lines 263–297) — post-launch report template

File header:
```markdown
# Launch Templates

## 上线沟通模板

### 内部沟通

```markdown
# 上线通知：[功能名称]

## 上线时间
[日期] [时间]

## 上线内容
- 功能1：...
- 功能2：...

## 影响范围
- 影响：[说明]
- 不影响：[说明]

## 注意事项
- [ ] 上线期间可能会有短暂服务中断
- [ ] 上线后请关注[监控指标]

## 值班安排
- 技术值班：[姓名] [联系方式]
- 产品值班：[姓名] [联系方式]
```

### 外部沟通（用户公告）

```markdown
# 新功能上线通知

亲爱的用户：

我们很高兴地宣布，[功能名称]正式上线啦！

## 新功能介绍
[简洁说明功能价值]

## 如何使用
[使用指南]

## 常见问题
[FAQ]

如有问题，请联系客服：[联系方式]
```

## 上线报告模板

```markdown
# 上线报告：[功能名称]

## 基本信息
- 上线时间：[开始] - [结束]
- 上线类型：[全新产品/重大功能/常规迭代]
- 负责人：[姓名]

## 上线内容
1. [功能1]
2. [功能2]

## 上线结果
- [ ] 按计划完成
- [ ] 延期完成（原因：...）
- [ ] 回滚（原因：...）

## 数据表现
| 指标 | 上线前 | 上线后 | 变化 |
|-----|-------|-------|-----|
| DAU | ... | ... | ... |
| 错误率 | ... | ... | ... |
| 响应时间 | ... | ... | ... |

## 遇到的问题
1. [问题描述] - [解决方案]
2. [问题描述] - [解决方案]

## 后续计划
1. [待优化项1]
2. [待优化项2]
```
```

- [ ] **Step 3: Create `examples/launch-example.md`**

Create `plugins/super-product-manager/skills/launch/examples/launch-example.md` with the full `## 示例对话` section (lines 300–419): two example conversations showing skill responses to "准备上线了，帮我列个清单" and "新产品，这周五上线".

File header:
```markdown
# Launch Skill — Example Conversations

## 示例 1：用户说"准备上线了，帮我列个清单"

### 用户说："准备上线了，帮我列个清单"

**输出**：
> 等等，先确认几个事：
>
> 1. **上的是什么？** 新产品？新功能？Bug修复？
> 2. **什么时候上？** 今天？明天？周几？
> 3. **有回滚方案吗？** 出问题了怎么撤回来？
> 4. **有没有人值班？** 上线后谁盯着？
>
> 这些不清楚，上线清单也是白列。

## 示例 2：用户说"新产品，这周五上线"

### 用户说："新产品，这周五上线"

**输出**：
> ## 上线检查清单：新产品发布
>
> ---
>
> ⚠️ **重要提醒**：不建议周五上线新产品。如果出问题，周末没人处理。建议改到周二或周三。
>
> ---
>
> ### Pre-launch（上线前）- 必须完成
>
> | 检查项 | 负责人 | 验收标准 | 状态 |
> |-------|-------|---------|-----|
> | 功能验收完成 | 开发 | 所有P0/P1需求已实现 | ⬜ |
> | 测试通过 | 测试 | 无P0/P1缺陷 | ⬜ |
> | 性能测试通过 | 开发 | TPS>1000，响应<500ms | ⬜ |
> | 安全扫描通过 | 安全 | 无高危漏洞 | ⬜ |
> | 数据备份完成 | 运维 | 上线前数据已备份 | ⬜ |
> | 回滚方案确认 | 运维 | 回滚脚本已准备 | ⬜ |
> | 监控告警配置 | 运维 | 核心指标监控已配置 | ⬜ |
> | 用户文档更新 | 产品 | 帮助文档已上线 | ⬜ |
>
> ---
>
> ### 灰度发布方案
>
> **第1天（周四）**：内部测试（10-20人）
> - 验证：核心功能可用，无崩溃
>
> **第2天（周五）**：小灰度（1%用户）
> - 验证：错误率<0.5%，无用户投诉
>
> **第3天（周一）**：中灰度（10%用户）
> - 验证：性能正常，指标稳定
>
> **第4天（周二）**：大灰度（50%用户）
> - 验证：无异常，准备全量
>
> **第5天（周三）**：全量发布（100%用户）
>
> ---
>
> ### 回滚方案
>
> **回滚触发条件**（满足任一立即回滚）：
> - 错误率超过1%持续5分钟
> - 用户注册失败
> - 核心功能不可用
> - 用户投诉超过10单/小时
>
> **回滚操作**：
> 1. 代码回滚到上一版本（预计5分钟）
> 2. 验证服务恢复正常（预计5分钟）
> 3. 通知用户服务已恢复
>
> **回滚时间目标**：15分钟内完成
>
> ---
>
> ### 上线当天安排
>
> **值班人员**：
> - 技术值班：[姓名] [电话]
> - 产品值班：[姓名] [电话]
>
> **监控重点**：
> - 错误率（目标：<0.1%）
> - 响应时间（目标：<500ms）
> - 用户注册成功率（目标：>95%）
>
> **应对准备**：
> - 客服FAQ已准备
> - 用户公告模板已准备
> - 紧急联系群已建立
>
> ---
>
> ### 风险提示
>
> | 风险 | 概率 | 应对 |
> |-----|-----|-----|
> | 服务器压力不足 | 中 | 提前扩容，准备限流 |
> | 第三方接口异常 | 低 | 降级方案 |
> | 用户体验问题 | 中 | 提前内测收集反馈 |
>
> ---
>
> ### 上线后检查（上线后1小时、1天、1周）
>
> **1小时后**：
> - [ ] 核心指标正常
> - [ ] 无P0级别错误
> - [ ] 用户反馈正常
>
> **1天后**：
> - [ ] 数据表现符合预期
> - [ ] 用户投诉在可控范围
> - [ ] 性能指标稳定
>
> **1周后**：
> - [ ] 撰写上线报告
> - [ ] 收集改进建议
> - [ ] 规划下一版本
```

- [ ] **Step 4: Replace extracted sections in SKILL.md with summary links**

Replace `## 上线沟通模板` (lines 171–219) with:

```markdown
## 上线沟通模板

提供内部团队通知模板和外部用户公告模板。见 [`references/templates.md`](references/templates.md)。
```

Replace `## 上线报告模板` (lines 263–297) with:

```markdown
## 上线报告模板

上线后总结报告，包含基本信息、上线内容、结果、数据和后续计划。见 [`references/templates.md`](references/templates.md)。
```

Replace `## 示例对话` (lines 300–419) with:

```markdown
## 示例对话

见 [`examples/launch-example.md`](examples/launch-example.md)，包含完整的新产品上线检查清单生成示例。
```

- [ ] **Step 5: Verify line count**

```bash
wc -l plugins/super-product-manager/skills/launch/SKILL.md
```

Expected: ≤ 280 lines

- [ ] **Step 6: Commit**

```bash
git add plugins/super-product-manager/skills/launch/
git commit -m "feat(f5): extract templates+examples from launch SKILL.md"
```

---

## Task 5: SPM roadmap (413 → ~305 lines)

**Files:**
- Modify: `plugins/super-product-manager/skills/roadmap/SKILL.md`
- Create: `plugins/super-product-manager/skills/roadmap/examples/roadmap-examples.md`

**What to extract:** `## 示例对话` (lines 269–380, ~111 lines) → `examples/roadmap-examples.md`

- [ ] **Step 1: Confirm section boundaries**

```bash
grep -n "^## 示例对话\|^## 常见错误对照" plugins/super-product-manager/skills/roadmap/SKILL.md
```

Expected:
```
269:## 示例对话
381:## 常见错误对照
```

- [ ] **Step 2: Create `examples/roadmap-examples.md`**

Create `plugins/super-product-manager/skills/roadmap/examples/roadmap-examples.md` with the full `## 示例对话` section content (lines 269–380).

File header:
```markdown
# Roadmap Skill — Example Conversations

以下示例展示了不同场景下路线图技能的完整输出。

## 示例对话

### 用户说："帮我规划产品路线图"

**输出**：
> 规划路线图之前，先回答：
>
> 1. **产品愿景是什么？** 最终想做成什么样？
> 2. **规划多长时间？** 一个月？一个季度？一年？
> 3. **有多少资源？** 几个人？每周能投入多少时间？
> 4. **现在什么阶段？** 还没开始？已经有用户了？
>
> 不知道这些，路线图就是在画饼。

### 用户说："笔记工具，3个月，1个人"

**输出**：
> ## 产品路线图：笔记工具 MVP
>
> ### 基本信息
> - **产品**：简约笔记工具
> - **时间**：3个月（Q1 2024）
> - **资源**：1个全栈开发
> - **目标**：验证核心价值，获得100个活跃用户
>
> ---
>
> ### Now-Next-Later 路线图
>
> #### Now (第1个月) - 核心功能
> - [ ] 用户注册/登录
> - [ ] 创建笔记
> - [ ] 编辑笔记
> - [ ] 删除笔记
>
> #### Next (第2个月) - 增强体验
> - 笔记分类/标签
> - 搜索功能
> - 笔记分享
>
> #### Later (第3个月及以后) - 增长功能
> - 协作功能
> - 多端同步
> - 导出功能
>
> ---
>
> ### 里程碑规划
>
> #### M1: 用户系统 (Week 1-2)
> **目标**：用户可以注册登录
> **交付物**：
> - 手机验证码注册/登录
> - 个人中心页面
> **验收标准**：注册成功率>95%
> **负责人**：自己
> **依赖**：短信服务
>
> #### M2: 笔记核心功能 (Week 3-6)
> **目标**：用户可以创建编辑笔记
> **交付物**：
> - 创建笔记
> - Markdown编辑器
> - 自动保存
> **验收标准**：笔记保存成功率>99%
> **负责人**：自己
> **依赖**：M1完成
>
> #### M3: 用户体验优化 (Week 7-10)
> **目标**：提升使用体验
> **交付物**：
> - 分类标签
> - 搜索功能
> **验收标准**：搜索准确率>90%
> **负责人**：自己
> **依赖**：M2完成
>
> #### M4: 发布与验证 (Week 11-12)
> **目标**：上线并获取用户
> **交付物**：
> - 上线部署
> - 用户招募
> - 数据收集
> **验收标准**：100个注册用户，30个活跃用户
> **负责人**：自己
> **依赖**：M3完成
>
> ---
>
> ### 资源分析
>
> | 资源 | 需要 | 现有 | 备注 |
> |-----|-----|-----|-----|
> | 开发时间 | 20小时/周 | 20小时/周 | 周末+晚上 |
> | 短信费用 | ~500元 | 0元 | 需要自筹 |
> | 服务器 | ~200元 | 0元 | 需要自筹 |
>
> ---
>
> ### 风险提示
>
> 1. **时间风险**：一个人开发，遇到问题可能延期
>    - 应对：功能砍半，确保核心功能完成
>
> 2. **资源风险**：短信费用和服务器成本
>    - 应对：先用免费额度，后期再投入
>
> 3. **验证风险**：可能找不到目标用户
>    - 应对：提前在社群招募测试用户
```

- [ ] **Step 3: Replace section in SKILL.md**

Replace `## 示例对话` (lines 269–380) with:

```markdown
## 示例对话

见 [`examples/roadmap-examples.md`](examples/roadmap-examples.md)，包含多种路线图类型（Now-Next-Later、里程碑型）的完整输出示例。
```

- [ ] **Step 4: Verify line count**

```bash
wc -l plugins/super-product-manager/skills/roadmap/SKILL.md
```

Expected: ≤ 310 lines

- [ ] **Step 5: Commit**

```bash
git add plugins/super-product-manager/skills/roadmap/
git commit -m "feat(f5): extract example conversations from roadmap SKILL.md"
```

---

## Task 6: SPM prd (389 → ~276 lines)

**Files:**
- Modify: `plugins/super-product-manager/skills/prd/SKILL.md`
- Create: `plugins/super-product-manager/skills/prd/examples/prd-examples.md`
- Create: `plugins/super-product-manager/skills/prd/references/quick-reference.md`
- Create: `plugins/super-product-manager/skills/prd/references/prd-organization.md`

**What to extract:**
- `## 示例对话` (lines 96–144, ~48 lines) → `examples/prd-examples.md`
- `## 快速参考` (lines 291–326, ~35 lines) → `references/quick-reference.md`
- `## 分段式 PRD 组织规则` (lines 327–363, ~36 lines) → `references/prd-organization.md`

- [ ] **Step 1: Confirm section boundaries**

```bash
grep -n "^## 示例对话\|^## 技能衔接\|^## 快速参考\|^## 分段式 PRD\|^## 章节" \
  plugins/super-product-manager/skills/prd/SKILL.md
```

Expected:
```
96:## 示例对话
145:## 技能衔接
291:## 快速参考
327:## 分段式 PRD 组织规则
364:## 章节→技能协作映射
```

- [ ] **Step 2: Create `examples/prd-examples.md`**

Create `plugins/super-product-manager/skills/prd/examples/prd-examples.md` with the full `## 示例对话` section (lines 96–144).

File header:
```markdown
# PRD Skill — Example Conversations

## 示例对话

### 示例1：功能PRD

**用户输入**：
> 帮我写一个用户评论功能的PRD，包含评论发布、回复、点赞功能

**技能输出**：
- **PRD类型**：功能PRD
- **加载模板**：feature-prd.md
- **核心内容**：
  - 背景与目标：提升用户互动和内容沉淀
  - 用户故事：作为用户，我想发布评论以便表达观点
  - 功能范围：评论、回复、点赞（In范围）
  - 详细需求：评论发布流程、审核机制、通知推送
  - 验收标准：评论成功率、审核响应时间

### 示例2：数据PRD

**用户输入**：
> 需要设计用户行为分析的数据埋点方案，核心是追踪用户在APP内的行为路径

**技能输出**：
- **PRD类型**：数据PRD
- **加载模板**：data-prd.md
- **核心内容**：
  - 业务问题：需要了解用户行为路径以优化产品
  - 核心指标：页面访问深度、停留时长、转化率
  - 埋点方案：页面浏览、点击事件、停留时长
  - 分析框架：漏斗分析、路径分析、留存分析
  - 验收标准：埋点准确率≥95%

### 示例3：API PRD

**用户输入**：
> 需要对接微信支付接口，支持小程序支付和H5支付

**技能输出**：
- **PRD类型**：API PRD
- **加载模板**：api-prd.md
- **核心内容**：
  - 接口概述：对接微信支付系统
  - 接口列表：统一下单、查询订单、关闭订单、支付回调
  - 接口详情：请求参数、响应格式、错误码
  - 业务逻辑：支付流程、回调处理、对账机制
  - 验证标准：支付成功率、回调处理时间

---
```

- [ ] **Step 3: Create `references/quick-reference.md`**

Create `plugins/super-product-manager/skills/prd/references/quick-reference.md` with the `## 快速参考` section (lines 291–326).

File header:
```markdown
# PRD Quick Reference

## 快速参考

### PRD 核心章节（必备）

1. **文档信息**：版本、负责人、状态
2. **背景与目标**：为什么做、要达成什么
3. **需求描述**：具体做什么
4. **功能规格**：如何实现
5. **验收标准**：如何验证成功
6. **风险与依赖**：什么可能出问题

### 根据类型补充章节

**功能PRD补充**：
- 用户故事
- 交互流程
- 交互原型

**数据PRD补充**：
- 数据指标定义
- 埋点方案
- 分析框架

**API PRD补充**：
- 接口列表
- 接口详情
- 错误处理
- 安全要求

**通用PRD补充**：
- 用户分析
- 非功能需求
- 完整的上线计划

---
```

- [ ] **Step 4: Create `references/prd-organization.md`**

Create `plugins/super-product-manager/skills/prd/references/prd-organization.md` with the `## 分段式 PRD 组织规则` section (lines 327–363).

File header:
```markdown
# PRD Organization Rules

## 分段式 PRD 组织规则

### 适用场景

当 PRD 文档过大（超过模型 token 限制）或需要多人/多技能协作编辑时，可将 PRD 拆分为多个章节文件。

### 目录结构

```
/项目/docs/prd/
├── _index.md           # 索引文件（必读）：目录 + 各章节摘要
├── 01-background.md    # 背景与目标
├── 02-user-analysis.md # 用户分析 / 用户故事
├── 03-requirements.md  # 功能范围 / 需求描述
├── 04-specification.md # 详细需求 / 功能规格
├── 05-acceptance.md    # 验收标准
├── 06-metrics.md       # 数据指标
├── 07-non-functional.md# 非功能需求
├── 08-dependencies.md  # 依赖与风险
├── 09-launch-plan.md   # 上线计划
└── 10-appendix.md      # 附录
```

### 加载策略

1. **索引优先**：始终先读取 `_index.md` 了解整体结构和各章节摘要
2. **按需加载**：根据任务只加载需要的章节文件
3. **局部编辑**：修改特定章节时，只加载并编辑该章节文件

### 协作约束

- **不扩展结构**：PRD 只按既有模板章节输出，不新增章节
- **仅补充已存在章节**：只有 PRD 已包含某章节，才允许对应技能补充内容
- **保持一致性**：编辑后检查术语、引用是否与其他章节一致

---
```

- [ ] **Step 5: Replace sections in SKILL.md with summary links**

Replace `## 示例对话` (lines 96–144) with:

```markdown
## 示例对话

见 [`examples/prd-examples.md`](examples/prd-examples.md)，包含不同用户输入场景下 PRD 生成的完整示例。
```

Replace `## 快速参考` (lines 291–326) with:

```markdown
## 快速参考

常用 PRD 章节名称、优先级标签及格式速查。见 [`references/quick-reference.md`](references/quick-reference.md)。
```

Replace `## 分段式 PRD 组织规则` (lines 327–363) with:

```markdown
## 分段式 PRD 组织规则

当 PRD 内容超过单文件限制时的分段规则。见 [`references/prd-organization.md`](references/prd-organization.md)。
```

- [ ] **Step 6: Verify line count**

```bash
wc -l plugins/super-product-manager/skills/prd/SKILL.md
```

Expected: ≤ 280 lines
> Note: Removing ~119 lines and adding 9 lines of summaries yields ~276 lines (389−119+9). Target relaxed from 270 to 280 to match arithmetic.

- [ ] **Step 7: Commit**

```bash
git add plugins/super-product-manager/skills/prd/
git commit -m "feat(f5): extract examples+references from prd SKILL.md"
```

---

## Task 7: SPM user-story (384 → ~220 lines)

**Files:**
- Modify: `plugins/super-product-manager/skills/user-story/SKILL.md`
- Create: `plugins/super-product-manager/skills/user-story/references/card-template.md`
- Create: `plugins/super-product-manager/skills/user-story/examples/user-story-examples.md`

**What to extract:**
- `## 用户故事卡片模板` (lines 184–249, ~65 lines) → `references/card-template.md`
- `## 示例对话` (lines 250–351, ~101 lines) → `examples/user-story-examples.md`

- [ ] **Step 1: Confirm section boundaries**

```bash
grep -n "^## 用户故事卡片模板\|^## 示例对话\|^## 常见错误对照" \
  plugins/super-product-manager/skills/user-story/SKILL.md
```

Expected:
```
184:## 用户故事卡片模板
250:## 示例对话
352:## 常见错误对照
```

- [ ] **Step 2: Create `references/card-template.md`**

Create `plugins/super-product-manager/skills/user-story/references/card-template.md` with the full `## 用户故事卡片模板` section (lines 184–249), which contains the `## 用户故事：[故事名称]` subsection with fields for背景、验收标准、技术备注、依赖等.

File header:
```markdown
# User Story Card Template

## 用户故事卡片模板

```markdown
## 用户故事：[故事名称]

### 故事信息

| 项目 | 内容 |
|-----|-----|
| Story ID | US-001 |
| 优先级 | P0 |
| 复杂度 | 中等(3-5天) |
| 状态 | TODO |

---

### 故事描述

**作为** [用户角色]，
**我想要** [执行某个操作]，
**以便** [实现某个价值]。

---

### 验收标准 (Acceptance Criteria)

#### 场景 1：正常流程
- **Given**：[前置条件]
- **When**：[操作]
- **Then**：[预期结果]

#### 场景 2：边界情况
- **Given**：[边界条件]
- **When**：[操作]
- **Then**：[预期结果]

#### 场景 3：异常情况
- **Given**：[异常条件]
- **When**：[操作]
- **Then**：[预期结果]

---

### 业务规则

- BR-01：[规则描述]
- BR-02：[规则描述]

---

### 技术任务拆解

1. [ ] [任务1] (复杂度：低)
2. [ ] [任务2] (复杂度：中)
3. [ ] [任务3] (复杂度：高)

---

### 备注

- [ ] 需要注意的事项
- [ ] 待确认的问题
```
```

- [ ] **Step 3: Create `examples/user-story-examples.md`**

Create `plugins/super-product-manager/skills/user-story/examples/user-story-examples.md` with the full `## 示例对话` section (lines 250–351).

File header:
```markdown
# User Story Skill — Example Conversations

## 示例对话

### 用户说："写一个登录的用户故事"

**输出**：
> 登录有很多种，先确认几个问题：
>
> 1. **登录方式**：用户名密码？手机验证码？第三方登录？
> 2. **登录失败**：密码错误几次锁定？怎么解锁？
> 3. **登录状态**：保持多久？关浏览器失效还是记住7天？
> 4. **多设备**：同一账号能同时登录几个设备？

### 用户说："手机验证码登录"

**输出**：
> ## 用户故事：手机验证码登录
>
> ### 故事信息
>
> | 项目 | 内容 |
> |-----|-----|
> | Story ID | US-001 |
> | 优先级 | P0 |
> | 复杂度 | 中等(3-5天) |
> | 状态 | TODO |
>
> ---
>
> ### 故事描述
>
> **作为** 未登录用户，
> **我想要** 通过手机验证码快速登录，
> **以便** 无需记忆密码即可访问我的账户。
>
> ---
>
> ### 验收标准 (Acceptance Criteria)
>
> #### 场景 1：正常登录 - 已注册用户
> - **Given**：用户手机号已注册
> - **When**：用户输入手机号，获取验证码，输入正确验证码，点击登录
> - **Then**：登录成功，跳转到首页，显示用户信息
>
> #### 场景 2：正常登录 - 新用户自动注册
> - **Given**：用户手机号未注册
> - **When**：用户输入手机号，获取验证码，输入正确验证码，点击登录
> - **Then**：自动创建账户并登录，跳转到首页
>
> #### 场景 3：边界 - 验证码过期
> - **Given**：验证码已超过5分钟
> - **When**：用户输入过期验证码
> - **Then**：提示"验证码已过期，请重新获取"
>
> #### 场景 4：边界 - 验证码错误
> - **Given**：用户已获取验证码
> - **When**：用户输入错误的验证码
> - **Then**：提示"验证码错误，请重新输入"，允许重试
>
> #### 场景 5：边界 - 频繁获取验证码
> - **Given**：用户60秒内已获取过验证码
> - **When**：用户再次点击获取验证码
> - **Then**：按钮禁用，显示倒计时"X秒后重新获取"
>
> #### 场景 6：异常 - 短信发送失败
> - **Given**：短信服务异常
> - **When**：用户点击获取验证码
> - **Then**：提示"短信发送失败，请稍后重试"
>
> #### 场景 7：异常 - 手机号格式错误
> - **Given**：用户在输入框
> - **When**：用户输入非11位数字
> - **Then**：提示"请输入正确的手机号"，禁用获取验证码按钮
>
> ---
>
> ### 业务规则
>
> - BR-01：验证码有效期5分钟
> - BR-02：同一手机号60秒内只能获取一次验证码
> - BR-03：登录状态保持7天
> - BR-04：首次登录自动创建账户
>
> ---
>
> ### 技术任务拆解
>
> 1. [ ] 用户表设计 (复杂度：低)
> 2. [ ] 验证码表设计 (复杂度：低)
> 3. [ ] 发送验证码接口 (复杂度：中) - 对接短信服务商
> 4. [ ] 验证登录接口 (复杂度：中)
> 5. [ ] 登录页面UI (复杂度：低)
> 6. [ ] 登录状态管理 (复杂度：中)
>
> ---
>
> ### 备注
>
> - ⚠️ 需要对接短信服务商（阿里云/腾讯云），有成本
> - ⚠️ 需要加图形验证码防止短信被刷

---
```

- [ ] **Step 4: Replace sections in SKILL.md**

Replace `## 用户故事卡片模板` (lines 184–249) with:

```markdown
## 用户故事卡片模板

完整的用户故事卡片格式，包含背景、验收标准（Given/When/Then）、技术备注、依赖关系等字段。见 [`references/card-template.md`](references/card-template.md)。
```

Replace `## 示例对话` (lines 250–351) with:

```markdown
## 示例对话

见 [`examples/user-story-examples.md`](examples/user-story-examples.md)，包含登录、搜索、购物车等功能的完整用户故事生成示例。
```

- [ ] **Step 5: Verify line count**

```bash
wc -l plugins/super-product-manager/skills/user-story/SKILL.md
```

Expected: ≤ 230 lines (below repo budget 250)

- [ ] **Step 6: Commit**

```bash
git add plugins/super-product-manager/skills/user-story/
git commit -m "feat(f5): extract card-template+examples from user-story SKILL.md"
```

---

## Task 8: PT architectural-planning (442 → ~265 lines)

**Files:**
- Modify: `plugins/progress-tracker/skills/architectural-planning/SKILL.md`
- Create: `plugins/progress-tracker/skills/architectural-planning/references/planning-templates.md`
- Create: `plugins/progress-tracker/skills/architectural-planning/examples/example-conversation.md`

**What to extract:**
- Phase 2 decision template + Phase 3 architecture design templates + Phase 4 documentation template (lines 100–259, ~159 lines) → `references/planning-templates.md`
- `## Example Conversation` (lines 420–432, ~12 lines) + `## Questions to Ask` (lines 434–442, ~8 lines) → `examples/example-conversation.md`

- [ ] **Step 1: Confirm section boundaries**

```bash
grep -n "^### Phase 2\|^### Phase 3\|^### Phase 4\|^## Smart Recommendations\|^## Example Conversation\|^## Questions to Ask" \
  plugins/progress-tracker/skills/architectural-planning/SKILL.md
```

Expected:
```
96:### Phase 2: Technology Selection
125:### Phase 3: Architecture Design
200:### Phase 4: Decision Documentation
268:## Smart Recommendations
420:## Example Conversation
434:## Questions to Ask
```

> Note: `Before finalizing, validate that the document includes:` (line ~260) is paragraph text after the Phase 4 template block closes — it is not a heading and will not appear in grep output. Phase 4 ends at line ~259; `## Smart Recommendations` at line 268 confirms the boundary.

- [ ] **Step 2: Create `references/planning-templates.md`**

Create `plugins/progress-tracker/skills/architectural-planning/references/planning-templates.md` with content copied from lines 96–259 (Phase 2 through Phase 4 template bodies):

```markdown
# Architectural Planning Templates

## Phase 2: Technology Selection — Decision Template

```markdown
## 📦 Decision: <Component Name>

**Options**:

1. **[Option A]** - ⭐ Recommended
   - Pros: <advantage 1>, <advantage 2>
   - Cons: <disadvantage 1>
   - Best for: <use case>

2. **[Option B]**
   - Pros: <advantage 1>, <advantage 2>
   - Cons: <disadvantage 1>
   - Best for: <use case>

3. **[Option C]**
   - Pros: <advantage 1>, <advantage 2>
   - Cons: <disadvantage 1>
   - Best for: <use case>

**Context**: <specific project context>
**Recommendation**: [Option A] because <reasoning>

Choose [A/B/C] or suggest alternative:
```

## Phase 3: Architecture Design Templates

### System Architecture

```markdown
## 🏗️  System Architecture

### High-Level Structure

```
[Client Layer] → [API Gateway] → [Service Layer] → [Data Layer]
                      ↓                ↓
                 [Auth Service]  [Message Queue]
```

### Component Breakdown

**API Gateway**
- Responsibility: Routing, rate limiting, authentication
- Technology: <selected technology>
- Scaling: <horizontal/vertical>

**Service Layer**
- <Service 1>: <responsibility>
- <Service 2>: <responsibility>
- <Service 3>: <responsibility>

**Data Layer**
- <Database 1>: <data type>
- <Cache>: <usage pattern>
- <Message Queue>: <async processing>
```

### Data Model

```markdown
## 📊 Data Model

### Entities

**<Entity 1>**
- Fields: <key fields>
- Relationships: <relations to other entities>
- Volume: <estimated records>

**<Entity 2>**
- Fields: <key fields>
- Relationships: <relations to other entities>
- Volume: <estimated records>
```

### API Design (if applicable)

```markdown
## 🔌 API Design

### REST Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST   | /api/users | Create user | Required |
| GET    | /api/users/:id | Get user | Required |

### Data Flow

1. Client → Request → API Gateway
2. API Gateway → Validate Auth
3. API Gateway → Route to Service
4. Service → Business Logic
5. Service → Database/Cache
6. Response ← Service ← API Gateway ← Client
```

## Phase 4: Architecture Document Template

```markdown
# Architecture: <Project Name>

**Created**: <timestamp>
**Last Updated**: <timestamp>

## Technology Stack

| Component | Technology | Version | Justification |
|-----------|-----------|---------|---------------|
| Backend   | <choice>  | <ver>   | <reason>      |
| Database  | <choice>  | <ver>   | <reason>      |
| Cache     | <choice>  | <ver>   | <reason>      |

## Key Architectural Decisions

### ADR-001: <Decision Title>

**Status**: Accepted / Proposed / Deprecated

**Context**: <problem or situation>

**Decision**: <choice made>

**Consequences**:
- Positive: <benefit 1>, <benefit 2>
- Negative: <drawback 1>
- Risks: <risk 1>

**Alternatives Considered**:
1. <Alternative 1> - Rejected because <reason>
2. <Alternative 2> - Rejected because <reason>

## System Architecture

<architecture diagram or description>

## Data Model

<data model description>

## Integration Points

<external systems and APIs>

## Deployment Strategy

<deployment approach>

## Next Steps

1. Review architecture with team
2. Run `/prog init` to generate feature breakdown based on these decisions
3. Begin implementation with `/prog next`
```
```

- [ ] **Step 3: Create `examples/example-conversation.md`**

Create `plugins/progress-tracker/skills/architectural-planning/examples/example-conversation.md` with content from lines 420–442 (Example Conversation + Questions to Ask):

```markdown
# Architectural Planning — Examples and Guidance

## Example Conversation

**User**: `/prog plan Build a real-time chat application`

**Skill Response**:

1. **Analyze**: Real-time chat needs WebSocket, message persistence, online status
2. **Question**: Expected concurrent users?
3. **Recommend**:
   - Small scale (<1000): Node.js + Socket.io + Redis
   - Large scale (>10000): Go + WebSocket + Redis Cluster + RabbitMQ
4. **Document**: Save decisions to `docs/progress-tracker/architecture/architecture.md`
5. **Guide**: Suggest running `/prog init` next

## Questions to Ask

When planning architecture, clarify:
- **Scale**: Concurrent users, data volume, growth rate
- **Reliability**: Uptime requirements, fault tolerance needs
- **Performance**: Latency requirements, throughput targets
- **Security**: Authentication needs, data sensitivity
- **Team**: Size, expertise, development timeline
```

- [ ] **Step 4: Replace Phase 2/3/4 template bodies in SKILL.md**

Replace **Phase 2 decision template** (lines 99–124, the full fenced code block from `` ```markdown `` starting with `## 📦 Decision:` through the closing `` ``` `` before `### Phase 3`) with:

> **Pre-edit check (P2 guard):** Run `sed -n '97,98p' plugins/progress-tracker/skills/architectural-planning/SKILL.md` before editing. If lines 97–98 contain leading prose (e.g. `For each technical decision, present:`), expand the replacement range to include those lines (e.g. lines 97–124) so the prose isn't duplicated after the replacement.

```markdown
For each technical decision, present the decision template from [`references/planning-templates.md`](references/planning-templates.md#phase-2-technology-selection-decision-template).
```

Replace **Phase 3 architecture templates** (lines 130–199, the three fenced code blocks for System Architecture / Data Model / API Design, from the first `` ```markdown `` after `#### System Architecture` through the closing `` ``` `` after `← Client`) with:

```markdown
Create visual and textual architecture description using the templates in [`references/planning-templates.md`](references/planning-templates.md#phase-3-architecture-design-templates).
```

Replace **Phase 4 documentation template** (lines 204–259, the fenced code block from `` ```markdown `` starting `# Architecture: <Project Name>` through the closing `` ``` `` after `Begin implementation with \`/prog next\``) with:

```markdown
Create `docs/progress-tracker/architecture/architecture.md` using the template in [`references/planning-templates.md`](references/planning-templates.md#phase-4-architecture-document-template).
```

> Note: Line numbers reference the current file state before any edits in this task. Verify with `grep -n "### Phase 2:\|### Phase 3:\|### Phase 4:" SKILL.md` before editing.

Replace `## Example Conversation` + `## Questions to Ask` (lines 420–442) with:

```markdown
## Examples and Questions

See [`examples/example-conversation.md`](examples/example-conversation.md) for a full example conversation (real-time chat app) and complete list of clarifying questions to ask.
```

- [ ] **Step 5: Verify line count**

```bash
wc -l plugins/progress-tracker/skills/architectural-planning/SKILL.md
```

Expected: ≤ 280 lines

- [ ] **Step 6: Commit**

```bash
git add plugins/progress-tracker/skills/architectural-planning/
git commit -m "feat(f5): extract planning-templates+examples from architectural-planning SKILL.md"
```

---

## Task 9: PT bug-fix (431 → ~330 lines)

**Files:**
- Modify: `plugins/progress-tracker/skills/bug-fix/SKILL.md`
- Modify (append): `plugins/progress-tracker/skills/bug-fix/references/workflow.md`
- Modify (append): `plugins/progress-tracker/skills/bug-fix/references/integration.md`

**What to move:**
- `## Progress Manager Extensions` (SKILL.md lines 289–311, ~22 lines) + `## Data Structure` (lines 313–341, ~28 lines) → append to `references/integration.md`
- `## Priority Calculation` (lines 343–368, ~25 lines) + `## Scheduling Logic` (lines 370–388, ~18 lines) → append to `references/workflow.md`

- [ ] **Step 1: Confirm section boundaries and existing reference file sizes**

```bash
grep -n "^## Progress Manager Extensions\|^### Data Structure\|^## Priority Calculation\|^## Scheduling Logic\|^## Error Handling" \
  plugins/progress-tracker/skills/bug-fix/SKILL.md
wc -l plugins/progress-tracker/skills/bug-fix/references/workflow.md \
       plugins/progress-tracker/skills/bug-fix/references/integration.md
```

Expected section lines: 289, 313, 343, 370, 389. Reference files: ~285 and ~250 lines each.
> Note: `Data Structure` is a **`###` third-level heading** under `## Progress Manager Extensions`, not a `##` second-level heading.

- [ ] **Step 2: Append algorithm and data details to `references/workflow.md`**

Append to `plugins/progress-tracker/skills/bug-fix/references/workflow.md`:

```markdown
---

## Priority Calculation Algorithm

```python
def calculate_bug_priority(description, verification):
    severity_keywords = {
        "high": ["crash", "broken", "fail", "security", "崩溃", "失败"],
        "medium": ["slow", "error", "wrong", "慢", "错误"],
        "low": ["typo", "cosmetic", "minor", "拼写"]
    }

    for level, keywords in severity_keywords.items():
        if any(kw in description.lower() for kw in keywords):
            severity = level
            break

    scope = "wide" if len(verification["related_files"]) > 3 else "narrow"

    if severity == "high" or scope == "wide":
        return "high"
    elif severity == "low":
        return "low"
    return "medium"
```

## Scheduling Logic Algorithm

```python
def schedule_bug(bug, features):
    priority = bug["priority"]

    if priority == "high":
        return {"type": "before_feature", "feature_id": next_pending_feature["id"]}

    related = find_related_features(bug["description"], features)
    if related:
        return {"type": "after_feature", "feature_id": related[-1]["id"]}

    return {"type": "last"}
```
```

- [ ] **Step 3: Append CLI commands and data schema to `references/integration.md`**

Append to `plugins/progress-tracker/skills/bug-fix/references/integration.md`:

```markdown
---

## Progress Manager CLI Commands

```bash
# Add bug
plugins/progress-tracker/prog add-bug \
  --description "<desc>" \
  --status "<status>" \
  --priority "<high|medium|low>" \
  --scheduled-position "<before|after>:<feature_id>"

# Update bug status
plugins/progress-tracker/prog update-bug \
  --bug-id "BUG-XXX" \
  --status "<new_status>" \
  --root-cause "<cause>"

# List bugs
plugins/progress-tracker/prog list-bugs

# Remove bug (false positive)
plugins/progress-tracker/prog remove-bug "BUG-XXX"
```

## Bug Data Structure (progress.json)

```json
{
  "bugs": [
    {
      "id": "BUG-001",
      "description": "登录后会话丢失",
      "status": "pending_investigation",
      "priority": "medium",
      "created_at": "2025-01-29T14:30:00Z",
      "quick_verification": {
        "code_exists": true,
        "related_files": ["auth/session.js"],
        "reproducibility": "medium",
        "confidence": "possible"
      },
      "scheduled_position": {
        "type": "before_feature",
        "feature_id": 3,
        "reason": "可能影响 Dashboard"
      }
    }
  ],
  "current_bug_id": null
}
```
```

- [ ] **Step 4: Replace the four sections in SKILL.md with summary links**

Replace `## Progress Manager Extensions`（含其 `### Data Structure` 子节，lines 289–341）with:

```markdown
## Progress Manager Extensions

Four CLI commands: `add-bug`, `update-bug`, `list-bugs`, `remove-bug`. Full command signatures and bug data schema (progress.json structure) in [`references/integration.md`](references/integration.md).
```

Replace `## Priority Calculation` + `## Scheduling Logic` (lines 343–388) with:

```markdown
## Priority and Scheduling Algorithms

Priority is calculated from severity keywords (high/medium/low) + scope (wide if > 3 related files). Scheduling places high-priority before next feature, medium after related feature, low at end. Full algorithms in [`references/workflow.md`](references/workflow.md).
```

- [ ] **Step 5: Verify line count**

```bash
wc -l plugins/progress-tracker/skills/bug-fix/SKILL.md
```

Expected: ≤ 340 lines

- [ ] **Step 6: Commit**

```bash
git add plugins/progress-tracker/skills/bug-fix/SKILL.md \
        plugins/progress-tracker/skills/bug-fix/references/workflow.md \
        plugins/progress-tracker/skills/bug-fix/references/integration.md
git commit -m "feat(f5): move algorithms+data-structure to references in bug-fix SKILL.md"
```

---

## Task 10: PT feature-breakdown (370 → ~290 lines)

**Files:**
- Modify: `plugins/progress-tracker/skills/feature-breakdown/SKILL.md`
- Create: `plugins/progress-tracker/skills/feature-breakdown/references/templates.md`
- Create: `plugins/progress-tracker/skills/feature-breakdown/examples/conversations.md`

**What to extract:**
- Output format template blocks at `## Feature Breakdown: <Project Name>` (lines 223–237 and 279–320, ~55 lines combined) → `references/templates.md`
- `## Example Conversations` (lines 344–362, ~18 lines) → `examples/conversations.md`

- [ ] **Step 1: Confirm section boundaries**

```bash
grep -n "^## Feature Breakdown:\|^## Smart Decision Making\|^## Integration with progress_manager\|^## Output Format\|^## Common Patterns\|^## Example Conversations\|^## Key Questions" \
  plugins/progress-tracker/skills/feature-breakdown/SKILL.md
```

Expected:
```
223:## Feature Breakdown: <Project Name>
238:## Smart Decision Making
258:## Integration with progress_manager.py
274:## Output Format
279:## Feature Breakdown: <Project Name>
321:## Common Patterns
344:## Example Conversations
363:## Key Questions to Answer
```

- [ ] **Step 2: Create `references/templates.md`**

Create `plugins/progress-tracker/skills/feature-breakdown/references/templates.md` with both `## Feature Breakdown: <Project Name>` template instances (lines 223–237 and 279–320), which contain the full markdown template for presenting feature breakdowns to users.

File header:
```markdown
# Feature Breakdown Templates

## Feature Breakdown Display Template (Short Form)

Used after initial breakdown generation (SKILL.md lines 223–237):

```markdown
## Feature Breakdown: <Project Name>

Based on your architecture (Node.js + Express + PostgreSQL):
✓ Using Sequelize for database models
✓ Using Express Router for API endpoints
✓ Using Joi for validation

I've broken this down into N features:
...

```

Each feature must include explicit architecture alignment:
- `Architecture constraints`: list of referenced `CONSTRAINT-*` IDs from `docs/progress-tracker/architecture/architecture.md`
- `Contract touchpoints`: interface/state/failure sections this feature implements
```

## Feature Breakdown Display Template (Full Form)

Used for output format reference (SKILL.md lines 279–320):

```markdown
## Feature Breakdown: <Project Name>

I've broken this down into N features:

1. **<Feature 1 Name>**
   - Architecture constraints: <CONSTRAINT-...>
   - Contract touchpoints: <interface/state/failure>
   - Test steps:
     - <step 1>
     - <step 2>

2. **<Feature 2 Name>**
   - Architecture constraints: <CONSTRAINT-...>
   - Contract touchpoints: <interface/state/failure>
   - Test steps:
     - <step 1>
     - <step 2>

...

Initialized progress tracking.
```

**At the end, ALWAYS output the Context Handoff Block:**

```markdown
---
**Paste into a new session to start first feature:**

/progress-tracker:prog-next

Project: <project_name> | 0/<total_features> done
ProjectRoot: <abs_project_root>
→ Context pre-loaded. Auto-selects and starts first pending feature.
---
```

Get the `ProjectRoot` by running:
```bash
pwd -P
```
```

- [ ] **Step 3: Create `examples/conversations.md`**

Create `plugins/progress-tracker/skills/feature-breakdown/examples/conversations.md` with the `## Example Conversations` section (lines 344–362):

```markdown
# Feature Breakdown — Example Conversations

## Example Conversations

**User**: "/prog init Build a task management app with CRUD operations"

**Your response**:
1. Analyze: This is a complex goal needing breakdown
2. Identify features: task model, create endpoint, read endpoint, update endpoint, delete endpoint, basic UI
3. Define test steps for each
4. Call progress_manager.py to initialize
5. Present breakdown to user

**User**: "/prog init Add dark mode toggle"

**Your response**:
1. Analyze: This is a simple, single feature
2. Define test steps: check toggle exists, verify theme changes, confirm persistence
3. Add as single feature to existing/new tracking
4. Confirm to user
```

- [ ] **Step 4: Replace extracted sections in SKILL.md**

Replace **first** `## Feature Breakdown: <Project Name>` block (lines 223–237 — the one immediately following `### Communicating Architecture Awareness`) with:

```markdown
## Feature Breakdown: <Project Name>

Present the breakdown using the short-form template in [`references/templates.md`](references/templates.md#feature-breakdown-display-template-short-form).
```

> Edit anchor: the first instance sits between `### Communicating Architecture Awareness` (line 218, above) and `## Smart Decision Making` (line 238, below). Include the preceding `### Communicating Architecture Awareness` heading as context — do NOT use the heading text alone, and do NOT use `## Integration with progress_manager.py` as an anchor (it is below `## Smart Decision Making`, nowhere near line 223).

Replace `## Output Format` + **second** `## Feature Breakdown: <Project Name>` block (lines 274–320 — the one immediately following `## Output Format\n\nPresent the breakdown to the user as:`) with:

```markdown
## Output Format

Use the full-form template in [`references/templates.md`](references/templates.md#feature-breakdown-display-template-full-form).
```

Replace `## Example Conversations` (lines 344–362) with:

```markdown
## Example Conversations

See [`examples/conversations.md`](examples/conversations.md) for example breakdowns of web app and CLI tool projects.
```

- [ ] **Step 5: Verify line count**

```bash
wc -l plugins/progress-tracker/skills/feature-breakdown/SKILL.md
```

Expected: ≤ 300 lines

- [ ] **Step 6: Commit**

```bash
git add plugins/progress-tracker/skills/feature-breakdown/
git commit -m "feat(f5): extract templates+examples from feature-breakdown SKILL.md"
```

---

## Task 11: Final Compliance Verification

**Files:** No changes.

- [ ] **Step 1: Run full compliance audit**

```bash
wc -l plugins/*/skills/*/SKILL.md | sort -nr | head -20
```

Expected results (all under 500 — SOP gate):
```
~433 plugins/package-manager/skills/package-manager/SKILL.md  ✓ (was 570)
~400 plugins/progress-tracker/skills/progress-status/SKILL.md ✓ (was 504)
~280 plugins/super-product-manager/skills/launch/SKILL.md     ✓ (was 458)
~270 plugins/progress-tracker/skills/architectural-planning/SKILL.md ✓ (was 442)
~340 plugins/progress-tracker/skills/bug-fix/SKILL.md         ✓ (was 431)
~300 plugins/progress-tracker/skills/feature-breakdown/SKILL.md ✓ (was 370)
~310 plugins/super-product-manager/skills/roadmap/SKILL.md    ✓ (was 413)
~276 plugins/super-product-manager/skills/prd/SKILL.md        ✓ (was 389)
~220 plugins/super-product-manager/skills/user-story/SKILL.md ✓ (was 384)
```

No file should be > 500 lines (SOP violation). Files still > 250 lines are flagged at repo budget level — note them but no further action required in this feature.

- [ ] **Step 2: Verify all new reference/example files have content**

```bash
find plugins -path "*/skills/*/references/*.md" -newer plugins/progress-tracker/docs/plans/2026-04-27-f5-progressive-disclosure-skill-files.md | sort
find plugins -path "*/skills/*/examples/*.md" -newer plugins/progress-tracker/docs/plans/2026-04-27-f5-progressive-disclosure-skill-files.md | sort
find plugins -path "*/skills/*/scripts/*.md" -newer plugins/progress-tracker/docs/plans/2026-04-27-f5-progressive-disclosure-skill-files.md | sort
```

Expected: all newly created files appear in output.

- [ ] **Step 3: Verify all relative links in modified SKILL.md files resolve**

```bash
for f in \
  plugins/package-manager/skills/package-manager/SKILL.md \
  plugins/progress-tracker/skills/progress-status/SKILL.md \
  plugins/progress-tracker/skills/architectural-planning/SKILL.md \
  plugins/progress-tracker/skills/bug-fix/SKILL.md \
  plugins/progress-tracker/skills/feature-breakdown/SKILL.md \
  plugins/super-product-manager/skills/launch/SKILL.md \
  plugins/super-product-manager/skills/roadmap/SKILL.md \
  plugins/super-product-manager/skills/prd/SKILL.md \
  plugins/super-product-manager/skills/user-story/SKILL.md; do
  dir=$(dirname "$f")
  rg -o '\[.*?\]\(([^)]+)\)' --replace '$1' "$f" | grep -v '^http' | while read link; do
    # Strip #anchor fragment before checking file existence
    filepath="${link%%#*}"
    target="$dir/$filepath"
    [ -f "$target" ] || echo "BROKEN LINK in $f: $link"
  done
done
```
> Note: Uses `rg` (ripgrep) instead of `grep -oP` for macOS compatibility. Strips `#anchor` fragments before `[ -f ]` check so links like `references/foo.md#section` resolve correctly.
> **Anchor validation is not performed** — only file existence is checked. Verify anchors manually for all links containing `#` fragments (especially Task 8 Phase 2/3/4 links into `planning-templates.md`).

Expected: no output (no broken links)

- [ ] **Step 4: Run contract test suite**

```bash
pytest -q plugins/progress-tracker/tests/test_command_discovery_contract.py
```

Expected: all PASS

- [ ] **Step 5: Final commit (if any cleanup needed)**

If any minor fixes were needed during verification:
```bash
git add -p  # review and stage only relevant fixes
git commit -m "feat(f5): fix link integrity after progressive disclosure extraction"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Audit line counts (`wc -l` in Tasks 1 and 11)
- ✅ Move long examples/templates to references/examples/scripts (Tasks 2–10)
- ✅ Keep link integrity (Task 11 link checker)
- ✅ Run discovery contract test (Tasks 3 and 11)
- ✅ SOP violations fixed (package-manager 570→433, progress-status 504→400)
- ✅ Repo budget applied to all >250 line files in scope

**Placeholder scan:** All "Create file" steps now contain the full verbatim content inlined directly in the plan. No `...（原文全部内容）...` placeholders remain in executable steps. The plan is self-contained and does not require workers to look up source files for template/example content.

**Type consistency:** No code types involved — all markdown file moves. Section names match between tasks and verification commands.
