# Fix Atlas Agent Invalid Model ID (oh-my-opencode)

## Context

用户遇到错误：`Agent atlas's configured model anthropic/claude-sonnet-4-5 is not valid`，并且在 `opencode debug agent atlas` 中观察到 Atlas 的模型来源不是 `~/.config/opencode/oh-my-opencode.json`。

本次排查在本机环境中确认了以下关键事实（均可复现/验证）：

- Atlas agent **由 oh-my-opencode 插件内置创建**，不是通过 `~/.config/opencode/oh-my-opencode.json` 明确声明。
  - 证据：`/Users/siunin/.cache/opencode/node_modules/oh-my-opencode/dist/index.js:53427` 定义 `createAtlasAgent()`，并在 `getDefaultAgents()`（同文件 `~54022` 附近）里把它注入 `result["atlas"]`。
- Atlas 的默认模型来自插件的 `AGENT_MODEL_REQUIREMENTS.atlas.fallbackChain`。
  - 证据：`/Users/siunin/.cache/opencode/node_modules/oh-my-opencode/dist/index.js:5008-5014`。
- 插件在“模型可用性”判断中会读取 OpenCode 的缓存（`~/.cache/opencode/models.json`），并根据“connected providers”过滤，但如果 connected providers 包含 `anthropic`，就会把 `anthropic/claude-sonnet-4-5` 视为可选并优先命中。
  - 证据：`/Users/siunin/.cache/opencode/node_modules/oh-my-opencode/dist/index.js:5199-5300`（`fetchAvailableModels()` + `fuzzyMatchModel()` + `resolveModelWithFallback()`）。

因此：**Atlas 选错 provider 的根因**通常是「fallbackChain 把 anthropic 放在最前」+「connected providers / models cache 让插件误以为 anthropic 可用」，从而解析出 OpenCode 当前并不认可的 `anthropic/claude-sonnet-4-5`。

本计划的策略：

1) 先快速“止血”：在 `~/.config/opencode/oh-my-opencode.json` 中显式覆盖 `agents.atlas.model` 到一个已确认可用的模型。
2) 再做“根因治理”：让模型选择逻辑只会落到真实可用/已连接的 provider（避免以后再次回退到 anthropic/opencode 等并触发同类问题）。

---

## Task Dependency Graph

| Task | Depends On | Reason |
|------|------------|--------|
| Task 1 | None | 需要先复现并采集当前真实配置/错误，避免盲改 |
| Task 2 | Task 1 | 必须在掌握“atlas 来自哪里/如何解析 model”后才能选最小修复点 |
| Task 3 | Task 1 | 需要从实际环境确认哪些模型/哪些 provider 被认为“connected/available” |
| Task 4 | Task 2, Task 3 | 覆盖 atlas model 需要基于“可用模型”做选择，并验证覆盖入口有效 |
| Task 5 | Task 4 | 验证修复是否生效依赖已落地覆盖配置 |
| Task 6 | Task 5 | 根因治理/长期修复必须在止血成功后进行，避免扩大变量 |

---

## Parallel Execution Graph

Wave 1 (Start immediately):
├── Task 1: 复现与采集证据 (no dependencies)
└── Task 2: 定位 atlas 配置来源与解析路径 (no dependencies)

Wave 2 (After Wave 1 completes):
└── Task 3: 识别可用模型与“connected providers”来源 (depends: Task 1)

Wave 3 (After Wave 2 completes):
└── Task 4: 通过 oh-my-opencode.json 覆盖 atlas 模型 (depends: Task 2, Task 3)

Wave 4 (After Wave 3 completes):
└── Task 5: 验证修复 + 回归验证其他 agent (depends: Task 4)

Wave 5 (After Wave 4 completes):
└── Task 6: 根因治理（防止未来回退到无效 provider）(depends: Task 5)

Critical Path: Task 1 → Task 3 → Task 4 → Task 5 → Task 6
Estimated Parallel Speedup: ~20%（Task 1/2 可并行）

---

## Tasks

### Task 1: 复现问题并采集“当前真实配置/错误”证据

**Description**: 在不修改任何配置前，收集“atlas 当前解析出的 model”和 OpenCode 报错信息，作为基线。

**Delegation Recommendation:**
- Category: `quick` - 纯命令/配置核对与信息采集
- Skills: [`git-master`] - 仅当需要把修复提交到代码仓库时才用；本任务通常不需要 git（可省略）

**Skills Evaluation:**
- ✅ INCLUDED `git-master`: 只有在后续决定对插件源码仓库做修复 PR 时才需要；若只改本地配置则可以不加载
- ❌ OMITTED `playwright`: 无浏览器操作
- ❌ OMITTED `frontend-ui-ux`: 无 UI/设计
- ❌ OMITTED `dev-browser`: 无浏览器自动化

**Depends On**: None

**Acceptance Criteria**:
- [ ] 运行 `opencode debug agent atlas` 并保存关键字段：`model.providerID` / `model.modelID`
- [ ] 运行能触发报错的实际命令（例如启动 session/调用 atlas 的入口），捕获完整错误：`Agent atlas's configured model ... is not valid`
- [ ] 记录版本：`opencode --version`、`oh-my-opencode --version`（或从 `~/.cache/opencode/node_modules/oh-my-opencode/package.json` 读取）

**References**:
- `/Users/siunin/.config/opencode/opencode.json` - 插件加载列表，确认 `oh-my-opencode` 已启用

---

### Task 2: 定位 atlas agent 配置来源（插件内置）与模型解析路径

**Description**: 用“可引用的证据链”回答：atlas 从哪里来的？为什么会选到 anthropic/claude-sonnet-4-5？覆盖点在哪里？

**Delegation Recommendation:**
- Category: `unspecified-low` - 需要读插件实现与追踪配置合并逻辑
- Skills: [`git-master`] - 仅当需要对插件源码做修改/提交时才启用

**Skills Evaluation:**
- ✅ INCLUDED `git-master`: 只有当要给 oh-my-opencode 提 PR / 本地打补丁才需要
- ❌ OMITTED `playwright`: 无
- ❌ OMITTED `frontend-ui-ux`: 无
- ❌ OMITTED `dev-browser`: 无

**Depends On**: None

**Acceptance Criteria**:
- [ ] 明确列出 atlas 的创建入口：`createAtlasAgent()` 与注入点（`result["atlas"] = orchestratorConfig`）
- [ ] 明确列出 atlas 默认 fallbackChain（至少第一候选 `anthropic/claude-sonnet-4-5`）
- [ ] 明确列出覆盖入口：`agents.atlas.model`（配置来自 `~/.config/opencode/oh-my-opencode.json` 或 `.opencode/oh-my-opencode.json`）

**References**:
- `/Users/siunin/.cache/opencode/node_modules/oh-my-opencode/dist/index.js:53427` - `createAtlasAgent(ctx)`
- `/Users/siunin/.cache/opencode/node_modules/oh-my-opencode/dist/index.js:54022` - `if (!disabledAgents.includes("atlas"))` 分支
- `/Users/siunin/.cache/opencode/node_modules/oh-my-opencode/dist/index.js:5008` - `AGENT_MODEL_REQUIREMENTS.atlas.fallbackChain`
- `/Users/siunin/.config/opencode/oh-my-opencode.json` - 当前未显式配置 atlas 的事实

---

### Task 3: 确认“可用模型集合”与 connected providers 的真实来源

**Description**: 解释“为什么会解析到 anthropic”：需要确认当前环境下 `connected providers` 是否包含 `anthropic`，以及 `models.json` 中有哪些 provider/model key。

**Delegation Recommendation:**
- Category: `unspecified-low` - 需要读缓存/运行诊断命令并解释结果
- Skills: [] - 纯诊断，无需额外技能

**Skills Evaluation:**
- ❌ OMITTED `git-master`: 不涉及 git
- ❌ OMITTED `playwright`: 无
- ❌ OMITTED `frontend-ui-ux`: 无
- ❌ OMITTED `dev-browser`: 无

**Depends On**: Task 1

**Acceptance Criteria**:
- [ ] 确认 `~/.cache/opencode/models.json` 是否包含 `anthropic` 与 `claude-sonnet-4-5`（以及是否包含 `google/antigravity-*`）
- [ ] 找到 OpenCode/oh-my-opencode 判断“connected providers”的数据来源（例如缓存文件、OpenCode API、登录状态）
- [ ] 若 `opencode models` 命令当前报错（例如 ENOENT jose 文件缺失），记录并给出最小修复路径（清缓存/重装/升级）

**References**:
- `/Users/siunin/.cache/opencode/models.json` - OpenCode 的 models cache
- `/Users/siunin/.cache/opencode/node_modules/oh-my-opencode/dist/index.js:5230` - `resolveModelWithFallback()`（会在 cache 空/不可信时走“first entry/connected provider”）
- `/Users/siunin/.cache/opencode/node_modules/oh-my-opencode/dist/index.js:5238` - `fetchAvailableModels()`（按 connected providers 过滤 models.json）

---

### Task 4: 通过配置覆盖 atlas 的 model（止血修复）

**Description**: 在 `~/.config/opencode/oh-my-opencode.json` 的 `agents` 下新增/补充 `atlas` 覆盖，显式指定一个已在 `opencode models` 中存在的模型。

**推荐默认选择**（与当前 sisyphus 保持一致）：

```json
{
  "agents": {
    "atlas": {
      "model": "google/antigravity-claude-sonnet-4-5-thinking",
      "variant": "max"
    }
  }
}
```

备选方案（如果你更希望 Atlas 只负责调度，不要太贵）：
- `google/antigravity-gemini-3-flash`（更快/更便宜，但推理与长上下文稳定性可能更差）
- `openai/gpt-5.2`（如果 OpenAI provider 已可用且你想统一高 IQ 调度）

**Delegation Recommendation:**
- Category: `quick` - 单文件 JSON 配置变更
- Skills: [] - 不涉及 git

**Skills Evaluation:**
- ❌ OMITTED `git-master`: 不提交到仓库
- ❌ OMITTED `playwright`: 无
- ❌ OMITTED `frontend-ui-ux`: 无
- ❌ OMITTED `dev-browser`: 无

**Depends On**: Task 2, Task 3

**Acceptance Criteria**:
- [ ] `~/.config/opencode/oh-my-opencode.json` 增加 `agents.atlas.model` 覆盖项（且 JSON 语法合法）
- [ ] `opencode debug agent atlas` 显示 Atlas 使用的新 model（providerID/modelID 对应覆盖值）
- [ ] 触发原本会报错的入口不再出现 “model ... is not valid”

**References**:
- `/Users/siunin/.config/opencode/oh-my-opencode.json` - 需要修改的配置文件

---

### Task 5: 验证修复是否生效（含回归验证）

**Description**: 在修复后，验证 Atlas 不再报错，并且 Sisyphus/Prometheus 等 agent 仍然能正常解析模型。

**Delegation Recommendation:**
- Category: `quick` - 纯验证
- Skills: []

**Skills Evaluation:**
- ❌ OMITTED `git-master`: 不涉及 git
- ❌ OMITTED `playwright`: 无
- ❌ OMITTED `frontend-ui-ux`: 无
- ❌ OMITTED `dev-browser`: 无

**Depends On**: Task 4

**Acceptance Criteria**:
- [ ] `opencode debug agent atlas` 输出中：`model.providerID` 与 `model.modelID` 都属于 `opencode models` 列表中的合法项
- [ ] `opencode debug agent sisyphus` / `opencode debug agent prometheus` 均正常（无 invalid model 报错）
- [ ] 运行一段最小的 Atlas 实际工作流（例如执行一个包含 delegate_task 的小计划，或触发 start-work 钩子），确认不会因模型校验失败而中断

**References**:
- `/Users/siunin/.config/opencode/opencode.json` - provider/plugin 组合是否仍一致

---

### Task 6: 根因治理（防止未来回退到 anthropic/opencode 等无效 provider）

**Description**: 止血后，解决“为什么 connected providers / models cache 会让插件选到 anthropic”的根因，降低未来升级/清缓存后复发概率。

可选治理路径（按推荐顺序）：

1) **固定 atlas 覆盖为长期配置**：即使 fallbackChain 变动，也不会自动回退。
2) **修复 connected providers 判定**：确保 OpenCode 当前只把你真实可用的 provider 标记为 connected（例如仅 google/openai）。
3) **升级 oh-my-opencode**：查看新版本是否改进了 provider-models whitelist cache 的生成与使用；必要时向上游提交 issue/PR（将 antigravity/实际 provider 纳入更可靠的 fallbackChain）。
4) **修复 OpenCode `opencode models` 命令报错**：如果存在 `ENOENT ... jose/dist/browser/index.js`，这会影响“模型列表/缓存刷新”，应通过清理并重建 `~/.cache/opencode/node_modules`（先备份）来恢复一致性。

**Delegation Recommendation:**
- Category: `unspecified-high` - 可能涉及多组件（OpenCode 缓存/插件版本/上游 issue）
- Skills: [`git-master`] - 如果要做上游修复 PR

**Skills Evaluation:**
- ✅ INCLUDED `git-master`: 上游修复/本地源码修复需要
- ❌ OMITTED `playwright`: 无
- ❌ OMITTED `frontend-ui-ux`: 无
- ❌ OMITTED `dev-browser`: 无

**Depends On**: Task 5

**Acceptance Criteria**:
- [ ] 解释清楚 connected providers 来源（并给出如何让它不再包含 anthropic 的具体操作步骤）
- [ ] 在不依赖 atlas override 的情况下（可临时注释掉覆盖做验证），fallbackChain 不会再解析到无效 provider
- [ ] 若需要：给出可复现的最小上游 issue（包含：当前 config、models cache 片段、错误日志、复现命令）

**References**:
- `/Users/siunin/.cache/opencode/models.json` - 证明 cache 内含 anthropic/opencode 等“目录级 provider”
- `/Users/siunin/.cache/opencode/node_modules/oh-my-opencode/dist/index.js:5199` - `fetchAvailableModels()` 的过滤逻辑

---

## Commit Strategy

- 默认：NO（本次修复主要发生在用户目录 `~/.config/opencode/oh-my-opencode.json` 与缓存目录，不进入 git 仓库）
- 如果决定给 oh-my-opencode 上游提 PR：
  - 单独分支
  - 原子提交（1 commit = 1 问题）
  - 提交信息建议：`fix(model-resolver): avoid selecting unconfigured providers for atlas`

---

## Success Criteria

- `opencode debug agent atlas` 显示的模型是一个 `opencode models` 可列出的合法 model（provider/model 都存在）
- 原始错误不再出现：`Agent atlas's configured model ... is not valid`
- `sisyphus/prometheus/oracle` 等其他 agent 不受影响，能正常启动并完成一次最小工作流
