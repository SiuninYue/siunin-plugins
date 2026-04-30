# 复杂度评分 v2

## 目标

优化 feature 复杂度评分机制，适配 vibe-coding 流程（test_steps 由 AI 生成而非人写），让评分更精准、更省 token、更顺畅。

## 当前问题

1. **两套评分系统并存**：Python `complexity_analyzer.py`（关键词计数）与 LLM rubric 各算各的，Python 版精度低（"user module file" > "distributed transaction"）
2. **rubric 内联在 coordinator 上下文**：70 行 `complexity-assessment.md` 随 SKILL.md 加载，占用 sonnet 上下文
3. **Test Complexity 维度依赖 test_steps**：vibe-coding 时 test_steps 不存在，无法评分
4. **权重不合理**：四维等权加总，File Impact（衡量规模）与 Design Decisions（衡量思考深度）同等权重
5. **返回值缺置信度**：评分不确定时无法通知下游做保守决策

## 方案设计

### 架构变更

```
当前：
  coordinator (sonnet) 加载 rubric → 阅读 feature → 评分 → 路由

优化后：
  coordinator (sonnet) → spawn haiku subagent（压缩 rubric + feature 描述）
                              ↓
                       返回 {score, bucket, model, path, confidence}
                              ↓
  coordinator 收结果 → persist → 路由
```

### rubric 维度重设计

| 维度 | 权重 | 评分标准 |
|------|------|----------|
| Design Decisions（设计决策） | ×4 | 无(0) / 小模式(3) / 模块/API(6) / 架构级(10) |
| Pattern Familiarity（模式熟悉度） | ×3 | 同模式(2) / 相似(5) / 新但标准(8) / 全新(10) |
| Integration Surface（集成面） | ×2 | 纯内部(2) / 1-2外部(5) / 3-5系统(8) / 跨服务(10) |
| File Impact（文件影响面） | ×1 | 1-2个(2) / 3-5(5) / 6-10(8) / 10+(10) |

满分 = 10×4 + 10×3 + 10×2 + 10×1 = **100 分**

### 分桶阈值

| 分数 | bucket | model | path |
|------|--------|-------|------|
| 0-37 | simple | haiku | direct_tdd |
| 38-62 | standard | sonnet | plan_execute |
| 63-100 | complex | opus | full_design_plan_execute |

### 返回值

```json
{
  "score": 28,
  "bucket": "complex",
  "model": "opus",
  "path": "full_design_plan_execute",
  "confidence": "high" | "medium" | "low"
}
```

confidence 处理：
- `high` → 直接路由
- `medium` → 路由但输出提示
- `low` → 升级一级（simple→standard→complex）

### 强制规则

```
强制 complex：架构重写 | 核心重构含未知依赖 | 跨模块大范围改动 | 描述模糊无法判断
强制 simple：单文件小 bug | 零设计决策 | 最小测试面
```

## 影响范围

- **新增**：`docs/roadmap/complexity-scoring-v2.md`（本文件）
- **删除/废弃**：`complexity_analyzer.py`、`complexity-assessment.md`（被 haiku prompt 替代）
- **修改**：`feature-implement/SKILL.md` Step 3——移除 rubric 加载，改为 spawn haiku subagent
- **新增**：haiku subagent prompt（压缩 rubric，~15 行）
- **不改**：`progress_manager.py` 的 `determine_complexity_bucket`（阈值缩放后映射逻辑不变）

## 待决策

- [ ] haiku subagent 是内联 prompt 还是独立 skill 文件
- [ ] confidence 字段是否需要在 `ai_metrics` 中持久化
- [ ] 阈值（37/62）是否需要实际数据校准
