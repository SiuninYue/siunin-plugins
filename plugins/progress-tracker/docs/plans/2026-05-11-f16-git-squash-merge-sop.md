# PT-F16: Git Squash Merge SOP — 集成到 prog-done 自动化流程

## 目标

在 `git-auto done` 和 `feature-complete` skill 中集成 Squash Merge 工作流，
使每个 feature 合入 main 时只产生一个语义完整的 commit，
杜绝中间 WIP/fix/chore 碎片污染 main 分支历史。

## 背景与动机

当前仓库 main 分支有 **379 个 commit**（统计日期 2026-05-11），
包含大量 feature 开发过程中的中间试错快照：

| 类型 | 数量 |
|------|------|
| feat | 163 |
| fix | 65 |
| chore | 50 |
| docs | 32 |
| merge | 25 |

典型碎片案例：
- **F8**（fail-closed release gate）：21 个 commit — 包括 WIP 步骤、typo 修复、配置调整
- **git-auto v2.2**：15 个 commit — 包括 dead branch 清理、refactor 微调
- **F5**（progressive disclosure）：13 个 commit — 包括格式修正、lint 调整

这些中间 commit 对代码阅读者提供零价值，只增加 `git log` 噪声、
`git bisect` 成本，且稀释了有意义的提交信息。

## 业界标准

| 公司/项目 | 做法 |
|-----------|------|
| GitHub 自身 | PR squash merge，一个 PR = 一个 commit |
| GitLab 默认 | Squash merge on merge request |
| VS Code 仓库 | Rebase + merge 保持线性历史 |
| Google/ Meta/ Microsoft | Main 只保留逻辑单元，中间过程在分支内消化 |

**统一原则**：main 分支只保留语义完整的"逻辑单元"，不保留开发的试错过程。

## 设计

### 变更前流程

```
feature 分支开发（自由 commit）
  → prog done 验收
    → git auto done（commit → push → PR → merge commit 到 main）
      → 分支清理
```

问题：merge commit 把 feature 分支的所有中间 commit 全部带入 main。

### 变更后流程

```
feature 分支开发（自由 commit）
  → prog done 验收
    → evaluator gate 通过
      → git auto done:
          1. git checkout main && git pull
          2. git merge --squash <feature-branch>
          3. git commit -m "feat(PT-XX): 功能描述

              ## 变更内容
              - 事项1
              - 事项2

              ## 验收
              - evaluator score: 100
              - pytest: all green

              Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
          4. git push
          5. git branch -d <feature-branch>
          6. git push origin --delete <feature-branch>（非阻塞）
      → tracker 记录 squash commit hash
```

### Commit Message 规范

```
feat(scope): 简短描述

## 变更内容
- 具体改动 1
- 具体改动 2

## 验收
- evaluator score: XX
- 测试结果

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

### 边界情况处理

| 情况 | 行为 |
|------|------|
| Feature 分支只有 1 个 commit | Squash 退化为普通 merge，commit message 规范化 |
| Squash 时产生冲突 | 退出并提示手动解决，不静默失败 |
| Cleanup 失败（权限/网络） | 打印 WARN 但 exit code 不变，feature 状态不阻塞 |
| main 上有未提交变更 | 阻止 squash，提示先 clean |

## 改动范围

| 文件 | 改动 |
|------|------|
| `skills/git-auto/SKILL.md` | `git auto done` — 替换普通 merge 为 squash merge |
| `skills/git-auto/references/closeout-and-recovery.md` | 补充 squash 冲突恢复指南 |
| `skills/feature-complete/SKILL.md` | Step 5 — 加入 squash merge 验证步骤 |
| `hooks/scripts/progress_manager.py` | `cmd_done()` cleanup — 适配 squash 后分支状态 |

## 可选增强：历史 remap 脚本

对已有 379 个 commit 提供一次性压缩工具：

```
prog squash-history --from <first_hash> --to <last_hash> --message "v1.0: 历史提交压缩"
```

流程：
1. `git rebase -i` 将指定范围 commit squash 为新 commit
2. 生成旧 hash → 新 hash 映射表
3. 遍历 `project_memory.json`、`sprint_ledger.jsonl`、`test_reports/*.json`
   替换所有旧 hash → 新 hash
4. 验证 JSON 格式完整性

> **注意**：此脚本为独立可选工具，不影响日常 prog-done 流程。

## 接受标准

1. `git auto done` 执行 squash merge，main 分支新增 1 个 commit
2. `project_memory.json` CAP hash = squash 后的最终 hash
3. Feature 分支自动清理（本地 + 远程）
4. `feature-complete` Step 5 显式包含 squash 检查项
5. 边界情况全覆盖（1 commit / 冲突 / cleanup 失败）

## 测试计划

| 层级 | 测试 | 说明 |
|------|------|------|
| 单元 | `test_squash_merge_flow.py` | 成功/冲突/cleanup 失败三个路径 |
| 集成 | Mock 5-commit 分支 | 执行 git auto done，验证 main +1 commit |
| 契约 | hash 一致性 | CAP hash == `git log main -1 --format=%H` |
| 回归 | 现有流程不变 | feature-complete 原有路径不受影响 |
| 边界 | 单 commit 分支 | Squash 退化为普通 merge |
| 手动 | 真实 feature 分支 | GitHub PR 页显示 "1 commit" |

## 风险

- **Squash 冲突**：多人同时修改同一文件时可能出现——需明确恢复指南
- **Hash 变更**：Squash 后 commit hash 变化，追踪文件需同步更新
- **回滚成本**：Squash 后无法单独 revert 中间某个改动——需接受"原子 feature"理念

## 范围外

- 不改变 PR 创建/审查流程
- 不强制旧 feature 重新 squash
- 不改其他插件（note-organizer、super-product-manager 等）的 git 工作流
