# Feature 7: 实现冲突处理与状态栏（优化版 v4）

## Context

**项目**: Progress Tracker UI - Markdown checkbox 编辑器
**需求**: 当多用户并发修改同一文档时，需要显示冲突提示并提供解决方案

**当前状态**:
- 后端已实现 409 Conflict 检测 (rev/mtime 校验)
- 前端仅显示简单文本提示 "检测到冲突，请刷新后重试"
- 状态栏已实现基础功能，通过 `/api/status-summary` 获取数据

**目标**:
1. 冲突发生时自动获取服务器最新版本（闭环数据一致性）
2. 显示冲突详情弹窗（独立 Drawer，不影响现有状态栏详情）
3. 提供稳健的 "逐行保留我的状态变更" 合并选项（处理行漂移）
4. 顶部状态栏（status-pill）支持专门的冲突状态显示（紫色，呼吸动画）

**代码审查发现修正**（v2 历史项）:
1. [P1] `/api/file` 查询参数使用 `path`（后端要求）
2. [P1] 冲突 Drawer 独立于现有状态栏详情系统（避免破坏 `openDrawer(panelType)` 和 `renderDrawerContent(panelType, detail)`）
3. [P1] 定义独立的 `escapeHtml` 工具函数（复用现有模式）
4. [P2] 复用现有 `splitContentLines` 函数（不重复定义）
5. [P2] 状态栏冲突使用 title 提示而非覆盖 risk-value 内容（保留真实风险数据）
6. [P2] `discardAndReload()` 正确恢复 `activePath`

**优化建议修正**（v4）:
1. [P1] **冲突锁提前释放修复**: 引入 `hasPendingConflict` 标志，在 `handleConflict` 中设置为 `true`，仅在 `mergeCheckboxStatus` 或 `discardAndReload` 完成后重置。移除 line 305 的 `isResolvingConflict = false` 过早重置。**✅ 已修复**
2. [P1] **行签名重建保存原始前缀**: 在 `state.pendingCheckboxUpdate` 中保存 `originalLinePrefix`（bullet + indent），用于稳健定位。不再硬编码 `-` 前缀。**✅ 已修复**
3. [P2] **独立冲突 Drawer CSS 补齐**: 补充 `.drawer-backdrop`、`.drawer-panel`、`.drawer-header`、`.drawer-close-btn` 等新类的 CSS 定义（复用现有样式变量）。**✅ 已修复**
4. [P2] **discardAndReload 文档列表刷新**: 在 `ui.activePath` 更新后调用 `renderFileList()` 以保持左侧激活态一致。**✅ 已修复**

**v4 新增修复** (P1 + P2):
1. [P1] **Drawer 打开类名与 CSS 选择器一致**: 修改 CSS 为 `.drawer.open .drawer-panel { right: 0; }`，与 JS 给 `#conflict-drawer` 加 open 匹配。
2. [P1] **冲突锁统一清理函数**: 新增 `clearConflictState()` 函数，在所有失败和退出路径调用，避免永久锁死。
3. [P1] **关闭 Drawer 显式决策**: 关闭按钮触发确认（"放弃未保存的修改"），禁用 backdrop 点击关闭，强制用户显式决策。
4. [P1] **删除强制重置代码**: 移除"强制重置 isResolvingConflict"代码，让 `mergeCheckboxStatus` / `discardAndReload` 自己管理状态生命周期。
5. [P2] **升级文本相似度算法**: 从字符集合相似度改为基于 token bigram 的 Jaccard 系数（兼顾中英文并对顺序敏感）。
6. [P2] **新增测试用例**: 添加状态清理和相似度算法的验证测试。

---

## Critical Files

| File | Purpose |
|------|---------|
| `plugins/progress-tracker/hooks/scripts/static/index.html` | 主要修改文件 |
| `plugins/progress-tracker/hooks/scripts/progress_ui_server.py` | 后端 API 参考 |

---

## Tasks

### Task 0: 新增状态清理单点函数（P2 修复）

**File**: `plugins/progress-tracker/hooks/scripts/static/index.html`
**Location**: 在 `setStatus` 函数后添加（约 line 851）

**Changes**:

```javascript
/**
 * 统一清理冲突状态（P2 修复）
 * 避免各分支手工 reset 遗漏导致永久锁死
 * @param options.keepDrawer - 是否保持 Drawer 打开（默认 false）
 * @param options.preserveConflictData - 保持冲突上下文用于重试（默认 false）
 */
function clearConflictState(options = {}) {
    const { keepDrawer = false, preserveConflictData = false } = options;

    // 非重试场景：清理冲突数据
    if (!preserveConflictData) {
        state.conflictData = null;
        state.pendingCheckboxUpdate = null;
        state.conflictRetryCount = 0;
    }

    // 操作态总是清理
    state.isResolvingConflict = false;
    state.isSaving = false;

    // 仅在"保留上下文 + 保持 Drawer 打开"时保持锁
    // 防止误用 preserveConflictData 导致隐藏锁死
    state.hasPendingConflict = keepDrawer && preserveConflictData;

    // 关闭 Drawer（除非指定保持）
    if (!keepDrawer) {
        closeConflictDrawer();
    }
}
```

**Verification**: 各失败分支调用此函数确保状态清理

---

### Task 1: 添加冲突状态样式

**File**: `plugins/progress-tracker/hooks/scripts/static/index.html`
**Location**: CSS section (after line 103)

**Changes**:

```css
/* 冲突状态 - 紫色主题，呼吸动画强调 */
.status.conflict {
    color: #9333ea;
    border-color: rgba(147, 51, 234, 0.3);
    background: rgba(147, 51, 234, 0.1);
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}

/* [修正3] 独立冲突 Drawer CSS 补齐（复用现有样式变量） */
.drawer-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(31, 41, 51, 0.5);
    backdrop-filter: blur(4px);
    z-index: 99;
}

.drawer-panel {
    position: fixed;
    top: 0;
    right: -420px;
    width: 420px;
    height: 100vh;
    background: var(--panel);
    border-left: 1px solid var(--line);
    box-shadow: -8px 0 24px rgba(31, 41, 51, 0.12);
    transition: right 280ms cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 100;
    display: flex;
    flex-direction: column;
}

/* [P1 修复] Drawer 打开类名与 CSS 选择器一致 */
.drawer.open .drawer-panel {
    right: 0;
}

.drawer-header {
    border-bottom: 1px solid var(--line);
    padding: 14px 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #ffffff;
}

.drawer-header h3 {
    margin: 0;
    font-size: 1.1rem;
}

.drawer-close-btn {
    width: 28px;
    height: 28px;
    border-radius: 6px;
    border: none;
    background: transparent;
    font-size: 1.2rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
}

.drawer-close-btn:hover {
    background: rgba(0, 0, 0, 0.06);
}

/* 冲突 Drawer 样式 */
.conflict-drawer {
    padding: 20px;
}

.conflict-table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
}

.conflict-table td {
    padding: 8px 0;
    border-bottom: 1px solid #e5e7eb;
}

.conflict-label {
    color: #6b7280;
    font-size: 13px;
    width: 120px;
}

.conflict-value {
    color: #111827;
    font-size: 14px;
    font-weight: 500;
}

.conflict-actions {
    display: flex;
    gap: 12px;
    margin-top: 20px;
}

.conflict-action-btn {
    flex: 1;
    padding: 12px 20px;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
}

.conflict-action-btn.primary {
    background: #9333ea;
    color: white;
}

.conflict-action-btn.primary:hover {
    background: #7e22ce;
}

.conflict-action-btn.secondary {
    background: white;
    color: #dc2626;
    border: 1px solid #dc2626;
}

.conflict-action-btn.secondary:hover {
    background: #fef2f2;
}

/* 冲突处理中状态 */
.conflict-action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
```

**Verification**: 样式应正确应用到冲突状态和 Drawer

---

### Task 2: 扩展状态对象与稳健冲突处理

**File**: `plugins/progress-tracker/hooks/scripts/static/index.html`
**Locations**:
- State object (~line 805)
- `updateCheckboxStatus()` function (~line 1079)
- 新增工具函数

**Changes**:

1. **扩展 state 对象** (在 line 812 后添加):
```javascript
// 在现有 state 对象中添加冲突相关字段
const state = {
    files: [],
    activePath: null,
    activeRev: "",
    activeMtime: 0,
    selectedCheckboxLine: null,
    menuTargetLine: null,

    // 冲突状态扩展（新增）
    conflictData: null,           // 冲突完整上下文
    pendingCheckboxUpdate: null,  // 待处理的 checkbox 更新
    isSaving: false,              // 保存中标志
    isResolvingConflict: false,   // 冲突处理中标志
    hasPendingConflict: false,    // [修正1] 有待处理冲突时保持锁定
    conflictRetryCount: 0,        // 冲突重试计数
    lastRequestId: 0,             // 请求序列号
    lastRequestTimestamp: 0       // 上次请求时间戳
};
```

2. **新增工具函数** (在 `splitContentLines` 后添加，约 line 892):
```javascript
/**
 * HTML 转义工具函数（独立定义，复用现有模式）
 */
function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}
```

3. **增强 `updateCheckboxStatus()` 函数** (替换 line 1079-1114):
```javascript
async function updateCheckboxStatus(lineIndex, nextStatus) {
    if (!state.activePath) {
        return;
    }

    // 并发控制：冲突处理中或正在保存时阻止操作
    // [修正1] 添加 hasPendingConflict 检查，防止冲突弹窗打开时继续编辑
    if (state.isSaving || state.isResolvingConflict || state.hasPendingConflict) {
        setStatus("请等待当前操作完成", "warn");
        return;
    }

    // 构建稳健行签名（用于服务器内容匹配）
    // 关键：使用重建的原始 markdown 行，而非包含 UI 图标的 DOM 文本
    // [修正2] 保存完整原始行前缀（bullet + indent），不硬编码 "-"
    const lineElement = document.querySelector(`.editor-line[data-line-index="${lineIndex}"]`);
    let originalMarkdownLine = "";
    let originalLinePrefix = "";  // [新增] 保存原始前缀（bullet + indent）

    if (lineElement) {
        const checkboxBtn = lineElement.querySelector('.checkbox-btn');
        const textSpan = lineElement.querySelector('.checkbox-text');

        if (checkboxBtn && textSpan) {
            // [修正2] 提取并保存完整行前缀（匹配现有 checkbox 行格式）
            // 支持: "- [ ]", "* [ ]", "+ [ ]", 以及缩进变体
            const lineText = lineElement.textContent || "";
            const checkboxMatch = lineText.match(/^(\s*[-*+]\s*\[)([ /xX\-!?])(\])(.*)$/);

            if (checkboxMatch) {
                originalLinePrefix = checkboxMatch[1];  // "- [", "* [", "+ [", 或带缩进
                const currentStatus = checkboxBtn.dataset.status || " ";
                const suffixText = textSpan.textContent || "";
                originalMarkdownLine = `${originalLinePrefix}${currentStatus}]${suffixText}`;
            }
        }
    }

    // 构建唯一请求ID
    const requestId = ++state.lastRequestId;
    state.lastRequestTimestamp = Date.now();
    state.isSaving = true;

    try {
        const payload = {
            file_path: state.activePath,
            line_index: lineIndex,
            new_status: nextStatus,
            base_rev: state.activeRev,
            base_mtime: state.activeMtime
        };

        const result = await fetchJson("/api/checkbox", {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        state.activeRev = result.rev;
        state.activeMtime = result.mtime;
        await loadFile(state.activePath, false);
        setStatus("已保存", "success");

    } catch (error) {
        if (error && error.status === 409) {
            // 保存冲突上下文
            state.pendingCheckboxUpdate = {
                lineIndex,
                newStatus: nextStatus,
                originalMarkdownLine,
                originalLinePrefix,  // [修正2] 保存原始前缀用于稳健定位
                requestId,
                targetLine: `checkbox-line-${lineIndex}`
            };

            state.conflictRetryCount = 0;

            // 进入冲突处理流程
            await handleConflict(error.payload, requestId);
        } else {
            setStatus("保存失败，请稍后重试", "error");
        }
    } finally {
        // [修正1] 使用 hasPendingConflict 判断是否保持锁定
        // 仅在无待处理冲突时重置 isSaving
        if (!state.hasPendingConflict) {
            state.isSaving = false;
        }
    }
}
```

4. **实现 `handleConflict()` 函数** (在 `updateCheckboxStatus` 后添加):
```javascript
async function handleConflict(conflictPayload, requestId) {
    // 请求过期检查
    if (requestId !== state.lastRequestId) {
        setStatus("冲突处理已过期", "warn");
        // [P1 修复] 使用 clearConflictState 统一清理
        clearConflictState();
        return;
    }

    state.isResolvingConflict = true;
    state.hasPendingConflict = true;  // [修正1] 保持锁定直到 merge/discard 完成
    setStatus("检测到冲突，正在获取最新版本...", "warn");

    try {
        // 步骤1: 获取服务器最新内容
        // 注意：使用 path 查询参数（后端要求）
        const serverFile = await fetchJson("/api/file?path=" + encodeURIComponent(state.activePath));

        // 步骤2: 校验 rev 确保数据一致性
        if (serverFile.rev !== conflictPayload.current_rev) {
            throw new Error("服务器版本在获取过程中已更新");
        }

        // 步骤3: 保存完整冲突上下文，**固化文件路径**
        state.conflictData = {
            serverRev: serverFile.rev,
            serverMtime: serverFile.mtime,
            serverContent: serverFile.content,
            localRev: state.activeRev,
            localMtime: state.activeMtime,
            pendingChange: state.pendingCheckboxUpdate,
            conflictDetectedAt: Date.now(),
            filePath: state.activePath  // 固化路径，防止文档切换导致错写
        };

        // 步骤4: 显示冲突弹窗（独立 Drawer）
        showConflictDrawer();
        setStatus("检测到冲突", "conflict");

        // [P1 修复] 不重置状态，保持锁定直到用户决策
        // isResolvingConflict = true; hasPendingConflict = true;

    } catch (fetchError) {
        console.error("冲突处理失败:", fetchError);

        // 重试逻辑（最多3次，指数退避）
        if (state.conflictRetryCount < 3) {
            state.conflictRetryCount++;
            const delay = Math.pow(2, state.conflictRetryCount) * 500;

            setStatus(`获取失败，${delay/1000}秒后重试...`, "warn");
            await new Promise(resolve => setTimeout(resolve, delay));

            await handleConflict(conflictPayload, requestId);
        } else {
            setStatus("无法获取最新版本，请手动刷新", "error");
            // [P1 修复] 使用 clearConflictState 统一清理
            clearConflictState();
        }
    }
}
```

---

### Task 3: 实现冲突 Drawer UI（独立系统）

**File**: `plugins/progress-tracker/hooks/scripts/static/index.html`
**Location**: 在 HTML body 中添加冲突 Drawer 结构，在 JS 中添加处理函数

**1. HTML 结构** (在现有 drawer 后添加，约 line 803 后):
```html
<!-- 冲突解决 Drawer（独立于状态栏详情 Drawer） -->
<div id="conflict-drawer" class="drawer" aria-hidden="true">
    <div class="drawer-backdrop" id="conflict-drawer-backdrop"></div>
    <div class="drawer-panel">
        <div class="drawer-header">
            <h3 id="conflict-drawer-title">冲突解决</h3>
            <button type="button" class="drawer-close-btn" id="conflict-drawer-close-btn" aria-label="关闭">✕</button>
        </div>
        <div id="conflict-drawer-content" class="drawer-content"></div>
    </div>
</div>
```

**2. JS 函数** (在 `handleConflict` 后添加):
```javascript
/**
 * 显示冲突解决 Drawer（独立系统，不影响现有状态栏详情）
 */
function showConflictDrawer() {
    const conflict = state.conflictData;
    if (!conflict) {
        setStatus("无冲突数据", "error");
        return;
    }

    const pending = conflict.pendingChange;
    const currentStatusLabel = getNextStatusLabel(pending.newStatus);

    // 构建冲突详情内容
    const contentHtml = `
        <div class="conflict-drawer">
            <table class="conflict-table">
                <tr><td class="conflict-label">服务器版本时间</td><td class="conflict-value">${escapeHtml(formatTimestamp(conflict.serverMtime))}</td></tr>
                <tr><td class="conflict-label">你的版本时间</td><td class="conflict-value">${escapeHtml(formatTimestamp(conflict.localMtime))}</td></tr>
                <tr><td class="conflict-label">你的修改</td><td class="conflict-value">行 ${pending.lineIndex + 1} → ${escapeHtml(currentStatusLabel)}</td></tr>
            </table>
            <p style="color: #6b7280; font-size: 13px; margin-top: 16px;">选择解决方式：</p>
            <div class="conflict-actions">
                <button type="button" class="conflict-action-btn primary" id="conflict-merge-btn">
                    逐行保留我的状态变更
                </button>
                <button type="button" class="conflict-action-btn secondary" id="conflict-discard-btn">
                    放弃我的修改，加载最新版本
                </button>
            </div>
        </div>
    `;

    document.getElementById("conflict-drawer-content").innerHTML = contentHtml;
    document.getElementById("conflict-drawer").classList.add("open");
    document.getElementById("conflict-drawer").setAttribute("aria-hidden", "false");
}

/**
 * 关闭冲突 Drawer
 */
function closeConflictDrawer() {
    document.getElementById("conflict-drawer").classList.remove("open");
    document.getElementById("conflict-drawer").setAttribute("aria-hidden", "true");
}

/**
 * 获取状态标签文本
 */
function getNextStatusLabel(statusChar) {
    const meta = checkboxStateLookup.get(statusChar);
    return meta ? meta.label : statusChar;
}
```

**3. 事件监听** (在现有事件监听后添加，约 line 1630):
```javascript
// [P1 修复] 关闭按钮触发确认：不允许仅关闭 UI
document.getElementById("conflict-drawer-close-btn").addEventListener("click", () => {
    const confirmed = confirm("关闭冲突弹窗将放弃未保存的修改，是否继续？");
    if (confirmed) {
        clearConflictState();
    }
});

// [P1 修复] 禁用 backdrop 点击关闭，强制用户显式决策
// document.getElementById("conflict-drawer-backdrop").addEventListener("click", closeConflictDrawer);

// 冲突解决按钮
document.getElementById("conflict-drawer-content").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;

    if (button.id === "conflict-merge-btn") {
        void mergeCheckboxStatus();
        return;
    }

    if (button.id === "conflict-discard-btn") {
        void discardAndReload();
        return;
    }
});
```

---

### Task 4: 实现稳健状态合并逻辑

**File**: `plugins/progress-tracker/hooks/scripts/static/index.html`
**Location**: 在 Task 3 函数后添加

```javascript
/**
 * 稳健合并用户的 checkbox 状态变更
 */
async function mergeCheckboxStatus() {
    const conflict = state.conflictData;
    if (!conflict) {
        setStatus("无冲突数据", "error");
        return;
    }

    state.isResolvingConflict = true;
    setStatus("正在稳健合并状态变更...", "info");

    // 禁用按钮防止重复点击
    document.getElementById("conflict-merge-btn").disabled = true;
    document.getElementById("conflict-discard-btn").disabled = true;

    try {
        // 1. 解析服务器内容（复用现有 splitContentLines）
        const serverLines = splitContentLines(conflict.serverContent);
        const pending = conflict.pendingChange;

        // 2. 稳健定位目标行
        // [修正2] 传入保存的原始前缀以支持稳健匹配
        const targetLineIndex = findTargetLineInContent(
            serverLines,
            pending.lineIndex,
            pending.originalMarkdownLine,
            pending.originalLinePrefix,  // 新增：原始前缀用于精确匹配
            3
        );

        if (targetLineIndex === -1) {
            setStatus("目标行已被删除或重写，无法合并", "warn");
            await discardAndReload();
            return;
        }

        // 3. 检查目标行是否仍为 checkbox
        const serverLine = serverLines[targetLineIndex] || "";
        const checkboxPattern = /^(\s*[-*+]\s*\[)([ /xX\-!?])(\])(.*)$/;
        const match = serverLine.match(checkboxPattern);

        if (!match) {
            setStatus("目标行已被修改为非checkbox，无法合并", "warn");
            await discardAndReload();
            return;
        }

        // 4. 发送合并请求（使用固化的文件路径）
        const payload = {
            file_path: conflict.filePath,
            line_index: targetLineIndex,
            new_status: pending.newStatus,
            base_rev: conflict.serverRev,
            base_mtime: conflict.serverMtime
        };

        const result = await fetchJson("/api/checkbox", {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        // 5. 成功合并：清理状态
        state.activeRev = result.rev;
        state.activeMtime = result.mtime;

        // 6. 重新加载文件（使用固化的路径）
        await loadFile(conflict.filePath, false);

        // [P1 修复] 使用 clearConflictState 统一清理
        clearConflictState({ keepDrawer: false });
        setStatus("状态变更已稳健合并", "success");

    } catch (error) {
        console.error("合并失败:", error);

        if (error && error.status === 409) {
            // 二次冲突
            state.conflictRetryCount++;

            if (state.conflictRetryCount <= 3) {
                const delay = Math.pow(2, state.conflictRetryCount) * 1000;
                setStatus(`再次检测到冲突，${delay/1000}秒后重试...`, "warn");

                await new Promise(resolve => setTimeout(resolve, delay));
                await handleConflict(error.payload, state.lastRequestId);
            } else {
                setStatus("多次合并失败，已加载最新版本", "warn");
                await discardAndReload();
            }
        } else {
            setStatus(`合并失败: ${error.message || "未知错误"}，请重试或放弃修改`, "error");
            // [P1 修复] 保持 Drawer 与冲突上下文，允许用户重试
            clearConflictState({ keepDrawer: true, preserveConflictData: true });
            // 恢复按钮状态
            document.getElementById("conflict-merge-btn").disabled = false;
            document.getElementById("conflict-discard-btn").disabled = false;
        }
    }
}

/**
 * 放弃修改并加载最新版本
 */
async function discardAndReload() {
    const conflict = state.conflictData;
    if (!conflict) {
        setStatus("无冲突数据", "error");
        return;
    }

    state.isResolvingConflict = true;
    setStatus("正在加载最新版本...", "info");

    try {
        // 使用固化的文件路径
        const targetPath = conflict.filePath;

        // 直接使用已获取的服务器内容渲染
        state.activeRev = conflict.serverRev;
        state.activeMtime = conflict.serverMtime;
        state.activePath = targetPath;  // 关键：恢复 activePath

        // 渲染服务器内容
        renderFileContent(conflict.serverContent || "");

        // 更新 UI 显示路径
        ui.activePath.textContent = targetPath;
        ui.activeTime.textContent = formatTimestamp(conflict.serverMtime);

        // [修正4] 刷新文档列表以保持左侧激活态一致
        renderFileList();

        // [P1 修复] 使用 clearConflictState 统一清理
        clearConflictState({ keepDrawer: false });
        setStatus("已加载最新版本", "success");

    } catch (error) {
        console.error("加载最新版本失败:", error);
        setStatus(`加载失败: ${error.message || "未知错误"}，请重试或继续合并`, "error");
        // [P1 修复] 保持 Drawer 与冲突上下文，允许用户重试
        clearConflictState({ keepDrawer: true, preserveConflictData: true });
        // 恢复按钮状态
        document.getElementById("conflict-merge-btn").disabled = false;
        document.getElementById("conflict-discard-btn").disabled = false;
    }
}

/**
 * 稳健行定位算法（五级策略 + P2 升级）
 * [修正2] 新增 originalLinePrefix 参数，用于精确前缀匹配
 * [P2 升级] 使用 Jaccard 相似度替代字符集合相似度
 */
function findTargetLineInContent(serverLines, originalIndex, originalText, originalLinePrefix, searchRadius = 3) {
    // 策略0: 精确前缀+文本匹配（最可靠）
    if (originalIndex < serverLines.length) {
        const line = serverLines[originalIndex];
        // 使用保存的原始前缀进行精确匹配
        if (line && line.startsWith(originalLinePrefix || "- [")) {
            const suffixMatch = line.substring((originalLinePrefix || "- [").length).includes(originalText.substring(0, 50));
            if (suffixMatch) {
                return originalIndex;
            }
        }
    }

    // 策略1: 原始位置直接匹配
    if (originalIndex < serverLines.length) {
        const line = serverLines[originalIndex];
        if (line && line.includes(originalText.substring(0, 30))) {
            return originalIndex;
        }
    }

    // 策略2: 文本签名匹配
    const originalFingerprint = createLineFingerprint(originalText);
    for (let i = 0; i < serverLines.length; i++) {
        const lineFingerprint = createLineFingerprint(serverLines[i]);
        if (lineFingerprint === originalFingerprint) {
            return i;
        }
    }

    // 策略3: 邻域搜索
    const start = Math.max(0, originalIndex - searchRadius);
    const end = Math.min(serverLines.length - 1, originalIndex + searchRadius);
    for (let i = start; i <= end; i++) {
        const line = serverLines[i];
        const checkboxPattern = /^(\s*[-*+]\s*\[)([ /xX\-!?])(\])(.*)$/;
        if (checkboxPattern.test(line) && line.includes(originalText.substring(0, 50))) {
            return i;
        }
    }

    // 策略4: 全文档范围搜索相似行
    const similarityThreshold = 0.8;
    let bestMatch = -1;
    let bestScore = 0;

    for (let i = 0; i < serverLines.length; i++) {
        const similarity = calculateTextSimilarity(originalText, serverLines[i]);
        if (similarity > bestScore && similarity >= similarityThreshold) {
            bestScore = similarity;
            bestMatch = i;
        }
    }

    return bestMatch;
}

function createLineFingerprint(text) {
    const normalized = text.trim().replace(/\s+/g, ' ').substring(0, 50);
    let hash = 0;
    for (let i = 0; i < normalized.length; i++) {
        hash = ((hash << 5) - hash) + normalized.charCodeAt(i);
        hash |= 0;
    }
    return hash.toString(16);
}

/**
 * [P2 升级] 文本相似度算法 - token bigram Jaccard
 * 对顺序敏感，比字符集合相似度更可靠，且兼容中英文混合文本
 */
function calculateTextSimilarity(text1, text2) {
    if (!text1 || !text2) return 0;

    // 词级 token（英文单词 + 数字 + 单个中文字符）
    const tokenPattern = /[a-z0-9]+|[\u4e00-\u9fa5]/gi;
    const tokens1 = (text1.toLowerCase().match(tokenPattern) || []);
    const tokens2 = (text2.toLowerCase().match(tokenPattern) || []);

    if (tokens1.length === 0 || tokens2.length === 0) return 0;

    // 使用 bigram 让顺序信息进入相似度计算
    const grams1 = tokens1.length > 1
        ? tokens1.slice(0, -1).map((t, i) => `${t} ${tokens1[i + 1]}`)
        : tokens1;
    const grams2 = tokens2.length > 1
        ? tokens2.slice(0, -1).map((t, i) => `${t} ${tokens2[i + 1]}`)
        : tokens2;

    // Jaccard 相似度 = |A ∩ B| / |A ∪ B|
    const set1 = new Set(grams1);
    const set2 = new Set(grams2);
    const intersection = new Set([...set1].filter(x => set2.has(x)));
    const union = new Set([...set1, ...set2]);

    return intersection.size / union.size;
}
```

---

## Test Verification

### Test Suite 1: 基本功能

**Test 1-1: API 参数验证**
- **操作**: 检查 `/api/file` 请求
- **期望**: 查询参数为 `path=`（非 `file_path=`）

**Test 1-2: 冲突 Drawer 独立性**
- **操作**: 打开状态栏详情 → 触发冲突 → 打开状态栏详情
- **期望**: 两个 Drawer 互不影响，各自独立工作

**Test 1-3: escapeHtml 函数**
- **操作**: 检查包含特殊字符的冲突内容
- **期望**: HTML 正确转义，无 XSS 风险

### Test Suite 2: 状态栏集成

**Test 2-1: 状态栏数据不丢失**
- **操作**: 触发冲突 → 解决冲突 → 刷新状态
- **期望**: risk-value 显示真实风险数据（来自 API）

**Test 2-2: 冲突状态显示**
- **操作**: 触发冲突
- **期望**: 顶部 status-pill 显示紫色"检测到冲突"，呼吸动画

### Test Suite 3: 文档切换场景

**Test 3-1: 文档切换后合并**
- **操作**: 冲突弹窗打开 → 切换文档 → 点击"合并"
- **期望**: 使用固化路径 `conflict.filePath`，正确合并

**Test 3-2: 文档切换后放弃**
- **操作**: 冲突弹窗打开 → 切换文档 → 点击"放弃"
- **期望**: `activePath` 恢复为 `conflict.filePath`，UI 显示正确文件

### Test Suite 4: 行漂移处理

**Test 4-1: 目标行偏移**
- **前置条件**: 服务器版本在目标行前新增2行
- **操作**: 点击"合并"
- **期望**: 稳健定位找到偏移后的行

---

### Test Suite 5: 状态清理与锁恢复 (P1 修复验证)

**Test 5-1: 冲突后直接关闭 Drawer**
- **操作**: 触发冲突 → 点击关闭按钮并确认
- **期望**: 状态清理完成，可继续编辑其他行

**Test 5-2: handleConflict 连续失败后可恢复**
- **操作**: 模拟 handleConflict 失败3次
- **期望**: 最终状态清理完成，未进入永久锁

**Test 5-3: 合并失败后重试**
- **操作**: 触发合并 → 模拟失败 → 重试
- **期望**: Drawer 保持打开且冲突上下文保留，按钮状态恢复，可重新操作

**Test 5-4: 放弃加载失败后重试**
- **操作**: 触发放弃 → 模拟加载失败 → 重试
- **期望**: Drawer 保持打开且冲突上下文保留，可再次选择"合并"或"放弃"

---

### Test Suite 6: 文本相似度算法验证 (P2 升级验证)

**Test 6-1: 相似文本高相似度**
- **操作**: `calculateTextSimilarity("完成 API 接口", "完成 API 接口设计")`
- **期望**: 相似度 > 0.4（共享 bigram 足够多）

**Test 6-2: 不同顺序低相似度**
- **操作**: `calculateTextSimilarity("完成 API 设计", "设计 API 完成")`
- **期望**: 相似度显著低于 Test 6-1（顺序不同导致 bigram 重叠下降）

**Test 6-3: 中英文混合支持**
- **操作**: `calculateTextSimilarity("实现用户注册功能", "实现用户登录功能")`
- **期望**: 正确计算相似度

---

## Acceptance Mapping

| Task | Acceptance Criteria |
|------|---------------------|
| Task 0 | `clearConflictState()` 函数在所有失败分支被调用，状态清理无遗漏，无永久锁 |
| Task 1 | 冲突状态显示紫色主题和呼吸动画，独立 Drawer CSS 样式完整 |
| Task 2 | 并发控制阻止重复编辑，冲突数据正确保存，hasPendingConflict 标志工作正常 |
| Task 3 | 冲突 Drawer 独立显示，不影响现有状态栏详情，关闭按钮触发确认 |
| Task 4 | 行定位算法能处理行漂移，文本相似度计算准确，合并/放弃操作使用固化路径 |

## Risks

| Risk | Impact | Mitigation |
|------|---------|-------------|
| 行漂移算法误判导致修改错误行 | 高 | 五级匹配策略 + Jaccard 相似度阈值 0.8，fallback 到放弃加载 |
| 并发操作导致状态锁死 | 中 | 统一 `clearConflictState()` 清理函数，hasPendingConflict 标志防重复 |
| 文档切换后路径固化失效 | 高 | 冲突数据中保存 `filePath`，所有操作使用固化路径不依赖 `state.activePath` |
| 相似度算法对中英文混合不准确 | 中 | 使用 token bigram + Jaccard 系数，兼顾中英文和顺序敏感性 |

## Time Estimate

| Task | Time |
|------|------|
| Task 0: 状态清理单点函数 | 15 min |
| Task 1: 冲突状态样式 | 20 min |
| Task 2: 状态扩展与稳健冲突处理 | 60 min |
| Task 3: 冲突 Drawer UI（独立系统） | 45 min |
| Task 4: 稳健合并逻辑 | 90 min |
| 测试验证与调试 | 90 min |
| **Total** | **5小时 20分钟** |
