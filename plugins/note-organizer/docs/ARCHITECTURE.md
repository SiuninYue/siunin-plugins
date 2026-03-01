# Note Organizer 运行时架构

## 组件分层

```
┌─────────────────────────────────────────────────────────┐
│                    命令层 (Commands)                      │
│  /note-process → 路由到 organize-note skill              │
│  /note-batch → 路由到 organize-note skill                │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                   技能层 (Skill)                          │
│  organize-note → 协调 Python 脚本 + AI 生成               │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                   脚本层 (Python)                         │
│  clean_timestamps.py    - 时间戳清理                      │
│  batch_scanner.py       - 文件扫描                        │
│  template_renderer.py   - 模板渲染                        │
│  file_writer.py         - 文件写入                        │
└─────────────────────────────────────────────────────────┘
```

## I/O 契约

### 输入
- 单文件: 文本文件路径（.txt, .md）
- 批量: Glob 模式（如 `./notes/*.txt`）

### 处理流程
1. 读取文件内容
2. Python 清理时间戳
3. AI 分析内容并生成元数据
4. 渲染模板
5. 写入输出文件

### 输出
- NotebookLM 格式: `<name>-notebooklm.md`
- Obsidian 格式: `<name>-obsidian.md`

## 运行时路径约定

**插件脚本路径**: 使用 `${CLAUDE_PLUGIN_ROOT}` 环境变量
- 命令层调用: `cd "${CLAUDE_PLUGIN_ROOT}" && python3 scripts/xxx.py`
- Python 内部: 使用 `Path(__file__)` 计算相对路径（安全）

## 错误处理
- 文件读取失败: 返回错误，跳过该文件
- AI 分类失败: 使用默认分类
- 写入冲突: 添加时间戳后缀
