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
