# 未来规划 / Roadmap

> 重大更新、架构改进、方向性计划的索引。每个计划的详细内容在各自文件中。

## 计划列表

| 状态 | 计划 | 文件 | 简述 |
|------|------|------|------|
| 设计中 | 复杂度评分 v2 | [complexity-scoring-v2.md](complexity-scoring-v2.md) | 移除 Python analyzer，改用 haiku subagent + 加权 rubric |
| 待实施 | progress_manager 模块化 | [progress-manager-modularization.md](progress-manager-modularization.md) | 提取 6 个核心模块为独立协作者，ADR-001/003/006 → DONE |
| 设计中 | 自主工作流 + 自我迭代 | [autonomous-workflow-self-iteration.md](autonomous-workflow-self-iteration.md) | 四层管线终局架构、promote 提升循环、对抗式标准评审、UI/UX 设计层 |

## 约定

- 文件名：`<主题>.md`，kebab-case
- 每个文件包含：目标、当前问题、方案设计、影响范围、待决策项
- 计划进入实施时，移入 `docs/plans/` 并按日期命名
- 废弃的计划移入 `docs/archive/plans/`
