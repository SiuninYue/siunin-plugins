# 文件扫描与读取 API 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 实现 GET /api/files 返回 markdown 文件列表，GET /api/file 获取文件内容和元数据

**架构:** 在现有的 ProgressUIHandler 中实现两个 GET 端点：
- `/api/files` - 扫描并返回 .claude 目录下的 markdown 文件列表
- `/api/file?path=<file>` - 获取指定文件的内容和元数据

**技术栈:** Python 标准库 (http.server, pathlib, json, hashlib)

---

## 状态说明

经过代码审查和测试验证，**此功能已在 Feature 1 中完整实现**：

### 已实现的功能

1. **GET /api/files** (progress_ui_server.py:226-261)
   - 扫描 `.claude` 目录下的所有 `.md` 文件
   - `progress.md` 优先排序
   - 返回包含 `name`, `path`, `mtime` 的 JSON 数组
   - 正确的 `Content-Type: application/json` 响应头

2. **GET /api/file** (progress_ui_server.py:180-224)
   - 通过 `path` 查询参数获取文件
   - 路径安全验证 (使用 `validate_path()`)
   - 返回 `content`, `mtime`, `rev` 的 JSON 对象
   - 正确的 `Content-Type: application/json` 响应头

### 验收测试结果

所有验收测试步骤均已通过：

```bash
# 1. 端口动态探测 ✅
PORT=$(lsof -nP -iTCP -sTCP:LISTEN | awk '$9 ~ /127\.0\.0\.1:(3737|3738|3739|3740|3741|3742|3743|3744|3745|3746|3747)$/ {split($9,a,":"); print a[2]; exit}')

# 2. GET /api/files ✅
curl -s "$BASE/api/files"
# [{"name": "progress", "path": ".claude/progress.md", "mtime": 1770481285}, ...]

# 3. progress.md 优先 ✅
curl -s "$BASE/api/files" | jq -r '.[0].name'
# "progress"

# 4. 无重复路径 ✅
curl -s "$BASE/api/files" | jq -r '.[].path' | sort | uniq -d | wc -l
# 0

# 5. GET /api/file ✅
curl -s "$BASE/api/file?path=.claude/progress.md" | jq '.content,.mtime,.rev'

# 6. Content-Type ✅
curl -s -D - -o /dev/null "$BASE/api/file?path=.claude/progress.md" | grep -i 'content-type'
# Content-Type: application/json
```

### 结论

**无需额外实现工作**。Feature 2 的所有功能已在 `c0e4db1` 提交中完成。

---

## 原始验收测试步骤

供 `/prog done` 使用：

1. 端口动态探测: `PORT=$(lsof -nP -iTCP -sTCP:LISTEN | awk '$9 ~ /127\.0\.0\.1:(3737|3738|3739|3740|3741|3742|3743|3744|3745|3746|3747)$/ {split($9,a,\":\"); print a[2]; exit}') && [ -z "$PORT" ] && PORT=3737 && BASE="http://127.0.0.1:$PORT"`

2. 测试 GET /api/files: `curl -s $BASE/api/files | head -20`

3. 验证扫描顺序（progress.md 优先）: `curl -s $BASE/api/files | jq -r '.[0].name' | grep progress`

4. 验证去重（无重复路径）: `curl -s $BASE/api/files | jq -r '.[].path' | sort | uniq -d | wc -l | grep 0`

5. 测试 GET /api/file: `curl -s "$BASE/api/file?path=.claude/progress.md" | jq '.content,.mtime,.rev'`

6. 测试 Content-Type（正确响应头）: `curl -s -D - -o /dev/null "$BASE/api/file?path=.claude/progress.md" | grep -i 'content-type:.*application/json'`
