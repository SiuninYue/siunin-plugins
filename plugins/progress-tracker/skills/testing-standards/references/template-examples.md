# Template Examples

This reference provides complete, ready-to-use templates for all testing document types.

## Feature Acceptance Report Template

```markdown
---
type: feature-acceptance
id: X
date: YYYY-MM-DD
status: passed
tester: []
build: []
environment: []
---

# Feature #{id} 验收测试报告

**测试日期**: []
**测试人员**: []
**环境**: macOS [version], [hardware]
**Build**: [commit hash]

---

## 测试前准备

### 构建和启动应用

1. **构建应用**:
   - 打开 Xcode: `open [Project].xcodeproj`
   - Clean Build Folder: Cmd+Shift+K
   - Build: Cmd+B
   - 确认构建成功，无错误

2. **运行应用**:
   - 在 Xcode 中按 Cmd+R 运行应用
   - 或者：Archive 后直接运行 .app 文件

3. **查看控制台输出**:
   - 在 Xcode: 打开 Debug Area (Cmd+Shift+Y)，查看底部控制台
   - 或使用 Console.app: 过滤 "[Process Name]" 进程

4. **验证环境**:
   - macOS 版本: _________
   - Xcode 版本: _________
   - Commit Hash: `git rev-parse --short HEAD`

---

## 测试结果

### 1. [Component Name]

测试步骤：
- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

**结果**: [ ] 通过 / [ ] 失败

**问题记录**:


---

### 2. [Another Component]

测试步骤：
- [ ] Step 1
- [ ] Step 2

**结果**: [ ] 通过 / [ ] 失败

**问题记录**:


---

## 总体评估

**功能完整性**: [ ] 完整 / [ ] 部分完整 / [ ] 不完整

**稳定性**: [ ] 稳定 / [ ] 偶尔问题 / [ ] 不稳定

**用户体验**: [ ] 良好 / [ ] 可接受 / [ ] 需改进

**是否通过验收**: [ ] 是 / [ ] 否

---

## 遗留问题

列出所有发现的问题：

1.
2.
3.

---

## 建议和改进

列出未来可改进的地方：

1.
2.
3.

---

## 签名

测试人员: _______________  日期: _______________

审核人员: _______________  日期: _______________
```

## Bug Fix Report Template

```markdown
---
type: bug-fix-report
id: BUG-XXX
date: YYYY-MM-DD
status: fixed
priority: high
---

# Bug #{id} 修复报告

**Bug ID**: BUG-XXX
**状态**: ✅ 已修复
**日期**: YYYY-MM-DD
**优先级**: [Critical/High/Medium/Low]

---

## 🐛 Bug 描述

**症状**: [Bug症状描述]

**影响**:
- [影响1]
- [影响2]

---

## 🔍 根本原因

[Root cause analysis with subsections as needed]

### Cause Category 1

1. **Detail 1**
   - [Explanation]

2. **Detail 2**
   - [Explanation]

---

## ✅ 解决方案

### 1. [Solution Part 1]

```[language]
[Code if applicable]
```

**作用**: [What this does]

---

### 2. [Solution Part 2]

[Description of solution]

**作用**: [What this does]

---

## 🧪 验证

[How the fix was verified]

- [ ] Verification step 1
- [ ] Verification step 2
- [ ] Verification step 3

**验证结果**: [ ] 通过 / [ ] 失败

---

## 📝 备注

[Additional notes, edge cases, or future improvements]
```

## Test Guide Template

```markdown
---
type: test-guide
id: X
date: YYYY-MM-DD
status: draft
---

# Feature #{id} 测试指南

**功能名称**: [Feature Name]
**相关文件**: [List relevant files]

---

## 测试环境要求

- macOS version: [required version]
- Xcode version: [required version]
- Other dependencies: [list]

---

## 测试前准备

1.
2.
3.

---

## 测试场景

### 场景 1: [Scenario Name]

**目的**: [What this tests]

**步骤**:
1. Step 1
2. Step 2
3. Step 3

**预期结果**:
- [Result 1]
- [Result 2]

---

### 场景 2: [Scenario Name]

**目的**: [What this tests]

**步骤**:
1. Step 1
2. Step 2

**预期结果**:
- [Result 1]

---

## 边界情况

- [ ] Case 1
- [ ] Case 2
- [ ] Case 3

---

## 故障排查

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| [Issue] | [Cause] | [Fix] |
| [Issue] | [Cause] | [Fix] |
```

## Minimal Template (Quick Reference)

### For Quick Feature Acceptance

```markdown
---
type: feature-acceptance
id: X
date: YYYY-MM-DD
status: passed
---

# Feature #{id} 验收

**日期**: YYYY-MM-DD
**Build**: [commit]

## 测试项

- [ ] Item 1
- [ ] Item 2
- [ ] Item 3

## 结果
**状态**: ✅ 通过 / ❌ 失败
**备注**: [Any notes]
```

### For Quick Bug Fix

```markdown
---
type: bug-fix-report
id: BUG-XXX
date: YYYY-MM-DD
status: fixed
---

# Bug #{id} 修复

**问题**: [Brief description]
**原因**: [Root cause]
**修复**: [Solution]
**验证**: ✅ 已测试
```

## Checkbox Quick Reference

| State | Markdown |
|-------|----------|
| Empty | `- [ ]` |
| Checked | `- [x]` |
| Partial | `- [~]` |
| In progress | `- [.]` |

## Section Headers (Chinese)

### For Feature Reports

- 测试前准备
- 测试结果
- 总体评估
- 遗留问题
- 建议和改进

### For Bug Reports

- 🐛 Bug 描述
- 🔍 根本原因
- ✅ 解决方案
- 🧪 验证
- 📝 备注

## Date Examples

```yaml
# Correct
date: 2024-01-20
date: 2024-12-31
date: 2024-06-15

# Incorrect
date: 2024/01/20    # Wrong separator
date: Jan 20, 2024   # Not ISO format
date: 01-20-2024     # Wrong order
```

## Status Examples

```yaml
# Feature acceptance
status: passed
status: passed-with-notes
status: failed
status: partial

# Bug fix
status: fixed
status: in-progress
status: verified

# Test guide
status: draft
status: approved
status: archived
```
