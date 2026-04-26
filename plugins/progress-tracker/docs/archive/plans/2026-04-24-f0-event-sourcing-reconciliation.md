# F0: Robust Progress State Architecture - Event Sourcing & Reconciliation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 progress tracker 实现 Event Sourcing 架构，通过 audit.log 作为唯一真相源，使 Git merge 后的状态丢失问题永久消除。

**Architecture:** append-only JSONL audit.log + Git union merge 解决并发冲突；`reconcile-state` 通过事件回放重建预期状态并修复 drift；写入 fail-closed（拒绝未知 event_type），读取 tolerant（warn+preserve 历史数据）；tracker_reset 作为 replay 边界清空已回放状态。

**Tech Stack:** Python 3.x, Git merge driver (union built-in), JSONL, pytest

---

## 设计决策（已确认）

- **Q1 去重**：两阶段 — Pass 1 按 id（id 冲突=重编号保留两者；id 相同+内容相同=删副本），Pass 2 按 (timestamp + event_type + feature_id) 语义去重
- **Q2 F9 恢复**：reconcile-state 检测 drift → 打印 backfill 预览 → 用户确认 → append `backfilled: true` 事件
- **Q3 Reconcile**：打印 diff + 自动修复 progress.json（不自动 commit）；`--check` 只读，`--auto-commit` 静默提交
- **Q4 白名单**：写入 fail-closed，读取 warn+preserve

---

## 重要实现约束（三轮审查沉淀）

1. **`load_progress_json()` / `save_progress_json()` 无 `project_root` 参数**：依赖全局 `_PROJECT_ROOT_OVERRIDE`。测试必须通过直接设置 `_pm._PROJECT_ROOT_OVERRIDE = root`（不走 `configure_project_scope` 的 git 检查路径）。
2. **`audit_log` 读写必须显式传 `project_root`**：`audit_log.read_audit_log/append_audit_record/generate_audit_id` 均需传 `project_root=effective_root`，其中 `effective_root = str(find_project_root())`。仅依赖 `PROGRESS_TRACKER_STATE_DIR` env var 会在生产跨 plugin 场景读错 audit.log。
3. **`AUDIT_LOG_AVAILABLE` 不存在**：用 `if audit_log is None: return`。
4. **`reconcile-state` 不加入 `MUTATING_COMMANDS`**：在 CLI dispatch 层按 `args.check` 分流——非 check 模式才加锁/route preflight；`--check` 是真只读。
5. **白名单必须包含现有生产事件类型**：`set_finish_state`, `schema_migration`, `evaluator_assessment`, `evaluator_backfill`。
6. **`tracker_reset` 是 replay 边界且有语义漏洞**：`_replay_audit_events()` 遇到 reset 时清空状态，但还需返回 `last_event_was_reset` 标志。reconcile 在该标志为 True 时，将所有 `completed=True` 的 feature 视为 drift（因 reset 后无后续完成事件意味着应恢复初始态）。
7. **auto-fix 必须强制写完整状态**：不用 `setdefault`，直接赋值；undo 时清理 `completed_at`/`commit_hash`。
8. **`.gitattributes` pattern 覆盖所有 plugin**：用 `plugins/*/docs/progress-tracker/state/audit.log merge=union`。
9. **现有 `test_audit_log.py` 使用非法 event_type**：加白名单后这些测试会炸。需在 Task 2 中同步修复。
10. **`project_scope` fixture 不得依赖 `PROGRESS_TRACKER_STATE_DIR` 掩盖路径 bug**：核心 progress_manager 测试通过 `audit_log.read_audit_log(project_root=str(project_scope["root"]))` 验证；仅 audit_log 模块单元测试保留 env var 注入。
11. **`configure_project_scope` 需要 cwd 在 git repo 内**：fixture 必须先 `_pm._PROJECT_ROOT_OVERRIDE = root` 直接设置，绕过 git 检查（tmp_path 不在 repo 内时会被拒绝）。
12. **`backfill-event` 幂等性须考虑 reset 边界**：`find_backfill_candidates()` 只看最后一次 `tracker_reset` 之后的 `feature_completed` 事件，不看全历史。
13. **`install-git-hooks` 须支持 worktree**：用 `git rev-parse --git-path hooks` 获取 hooks 目录，不能只查 `.git` 目录。
14. **`post-merge` hook 需覆盖所有受影响 plugin**：从 `CHANGED` 提取 `plugins/<name>`，逐个运行；standalone root 另处理。
15. **`record_feature_state_event()` 的写入失败处理**：对 I/O 写失败，必须 re-raise（打印 ERROR 后 raise），让调用方（done/undo/reset）感知失败。不能静默吞掉使主命令成功返回——这违反"事实源不可丢事件"约束。

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `.gitattributes` | **新建** | union merge，覆盖所有 plugin 的 audit.log |
| `hooks/scripts/audit_log.py` | **修改** | 白名单常量 + 写入校验 + 两阶段去重 |
| `hooks/scripts/progress_manager.py` | **修改** | reconcile-state / backfill-event / install-git-hooks；done/undo/reset 记录事件 |
| `hooks/scripts/post_merge_hook.sh` | **新建** | post-merge hook 脚本 |
| `tests/conftest.py` | **修改** | 添加 `project_scope` fixture 用于测试隔离 |
| `tests/test_audit_log.py` | **修改** | 修复已使用非法 event_type 的测试用例 |
| `tests/test_audit_log_dedup.py` | **新建** | 两阶段去重单元测试 |
| `tests/test_audit_log_whitelist.py` | **新建** | 白名单写入/读取测试 |
| `tests/test_reconcile_state.py` | **新建** | reconcile-state 命令集成测试 |
| `tests/test_backfill_event.py` | **新建** | backfill-event 命令测试 |
| `tests/test_git_hooks_install.py` | **新建** | install-git-hooks 测试 |

---

## Task 1: Git union merge 配置

**Files:**
- Create: `.gitattributes`（`/Users/siunin/Projects/Claude-Plugins/.gitattributes`）

- [ ] **Step 1: 创建 .gitattributes，覆盖所有 plugin**

```bash
cat > /Users/siunin/Projects/Claude-Plugins/.gitattributes << 'EOF'
# Progress tracker audit logs: union merge prevents conflicts on concurrent branch appends.
# Glob covers all plugins that use the progress-tracker layout.
plugins/*/docs/progress-tracker/state/audit.log merge=union
# Standalone repo root (if tracker_role=standalone at repo root)
docs/progress-tracker/state/audit.log merge=union
EOF
```

- [ ] **Step 2: 验证 Git 识别两条 pattern**

```bash
cd /Users/siunin/Projects/Claude-Plugins
git check-attr merge plugins/progress-tracker/docs/progress-tracker/state/audit.log
git check-attr merge plugins/note-organizer/docs/progress-tracker/state/audit.log
```

期望两行均输出 `merge: union`。

- [ ] **Step 3: 提交**

```bash
git add .gitattributes
git commit -m "feat(f0): configure audit.log union merge for all plugins via glob pattern"
```

---

## Task 2: 事件 schema 白名单（写入 fail-closed，读取 tolerant）

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/audit_log.py`
- Modify: `plugins/progress-tracker/tests/test_audit_log.py`（修复非法 event_type）
- Create: `plugins/progress-tracker/tests/test_audit_log_whitelist.py`

### Step 1: 写白名单测试（红灯）

创建 `plugins/progress-tracker/tests/test_audit_log_whitelist.py`：

```python
"""测试事件 schema 白名单：写入 fail-closed，读取 warn+preserve。"""
import json
import pytest
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import audit_log


def _make_record(event_type, id_="AUDIT-001"):
    return {
        "id": id_,
        "tx_id": "TX-20260424-120000-0001",
        "timestamp": "2026-04-24T12:00:00Z",
        "event_type": event_type,
    }


class TestAllowedEventTypesConstant:
    def test_constant_exists_and_is_frozenset(self):
        assert isinstance(audit_log.ALLOWED_EVENT_TYPES, frozenset)

    def test_contains_new_state_events(self):
        required = {
            "feature_completed", "feature_undone", "state_restored",
            "tracker_reset", "manual_state_override",
        }
        assert required.issubset(audit_log.ALLOWED_EVENT_TYPES)

    def test_contains_existing_production_events(self):
        """现有生产代码已在写入的类型必须在白名单内，否则静默丢数据。"""
        production = {
            "schema_migration", "evaluator_assessment", "evaluator_backfill",
            "set_finish_state",
        }
        assert production.issubset(audit_log.ALLOWED_EVENT_TYPES)

    def test_is_known_event_type_helper(self):
        assert audit_log.is_known_event_type("feature_completed") is True
        assert audit_log.is_known_event_type("totally_unknown") is False


class TestWhitelistWriteEnforcement:
    def test_known_event_type_allowed(self, temp_dir, monkeypatch):
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(temp_dir))
        audit_log.append_audit_record(_make_record("feature_completed"))
        assert (temp_dir / "audit.log").exists()

    def test_set_finish_state_allowed(self, temp_dir, monkeypatch):
        """生产事件 set_finish_state 不应被拒绝。"""
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(temp_dir))
        audit_log.append_audit_record(_make_record("set_finish_state"))

    def test_unknown_event_type_raises_valueerror(self, temp_dir, monkeypatch):
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(temp_dir))
        with pytest.raises(ValueError, match="Unknown event_type"):
            audit_log.append_audit_record(_make_record("totally_unknown_event"))

    def test_no_partial_write_on_rejection(self, temp_dir, monkeypatch):
        """被拒绝的写入不应留下任何文件内容。"""
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(temp_dir))
        log_path = temp_dir / "audit.log"
        try:
            audit_log.append_audit_record(_make_record("bad_event"))
        except ValueError:
            pass
        assert not log_path.exists() or log_path.read_text().strip() == ""


class TestWhitelistReadTolerance:
    def test_unknown_event_preserved_on_read(self, temp_dir, monkeypatch):
        """历史数据中的未知事件：读取时保留（不报错）。"""
        monkeypatch.setenv("PROGRESS_TRACKER_STATE_DIR", str(temp_dir))
        path = temp_dir / "audit.log"
        path.write_text(json.dumps({
            "id": "AUDIT-001", "tx_id": "TX-old",
            "timestamp": "2024-01-01T00:00:00Z",
            "event_type": "legacy_unknown_event",
        }) + "\n")
        records = audit_log.read_audit_log()
        assert len(records) == 1
        assert records[0]["event_type"] == "legacy_unknown_event"
```

- [ ] **Step 1: 运行，确认全部失败**

```bash
pytest plugins/progress-tracker/tests/test_audit_log_whitelist.py -v 2>&1 | head -25
```

期望：AttributeError 或 AssertionError（`ALLOWED_EVENT_TYPES` 不存在）

- [ ] **Step 2: 在 audit_log.py 添加白名单（AUDIT_LOG_FILENAME 常量之后）**

```python
# 事件类型白名单：写入路径 fail-closed；读取路径兼容历史数据（tolerant）
# 新增 event_type 时必须先加入此集合，否则 append_audit_record 拒绝写入。
ALLOWED_EVENT_TYPES: frozenset = frozenset({
    # 核心状态变更事件（Feature 0 新增）
    "feature_completed",
    "feature_undone",
    "state_restored",
    "tracker_reset",
    "manual_state_override",
    # 现有生产代码已写入的事件类型（不可移除，否则静默丢数据）
    "schema_migration",
    "evaluator_assessment",
    "evaluator_backfill",
    "set_finish_state",
})


def is_known_event_type(event_type: str) -> bool:
    """供读取路径判断是否为已知事件类型（不阻断，仅供 warn 决策）。"""
    return event_type in ALLOWED_EVENT_TYPES
```

- [ ] **Step 3: 在 append_audit_record() 的参数校验块末尾追加白名单检查**

在 `if not record.get("timestamp"):` 之后添加：

```python
    # 事件类型白名单 fail-closed：未知类型在写入时拒绝，防止污染事实源
    event_type = record.get("event_type", "")
    if event_type and event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(
            f"Unknown event_type '{event_type}'. "
            f"Add to ALLOWED_EVENT_TYPES in audit_log.py before use. "
            f"Known types: {sorted(ALLOWED_EVENT_TYPES)}"
        )
```

- [ ] **Step 4: 运行白名单测试，确认通过**

```bash
pytest plugins/progress-tracker/tests/test_audit_log_whitelist.py -v
```

期望：全部 passed

- [ ] **Step 5: 修复 test_audit_log.py 中使用非法 event_type 的用例**

定位非法类型：

```bash
grep -n '"test_event"\|"event1"\|"old"\|"new"' \
  plugins/progress-tracker/tests/test_audit_log.py
```

对每处非法类型，有两种修复策略：
- **策略 A**（推荐）：改为合法类型，例如 `"feature_completed"` 或 `"schema_migration"`
- **策略 B**：对于测试"读取容忍历史数据"的场景，直接写文件绕过 `append_audit_record`：

```python
# 直接写入文件（绕过白名单），模拟历史遗留数据
path = temp_dir / "audit.log"
path.write_text(json.dumps({
    "id": "AUDIT-001", "tx_id": "TX-test",
    "timestamp": "2026-01-01T00:00:00Z",
    "event_type": "legacy_custom_type",   # 模拟旧数据，不经过 append_audit_record
}) + "\n")
```

- [ ] **Step 6: 运行现有测试，确认无回归**

```bash
pytest plugins/progress-tracker/tests/test_audit_log.py -v --tb=short
```

期望：全部 passed

- [ ] **Step 7: 提交**

```bash
git add plugins/progress-tracker/hooks/scripts/audit_log.py \
        plugins/progress-tracker/tests/test_audit_log_whitelist.py \
        plugins/progress-tracker/tests/test_audit_log.py
git commit -m "feat(f0): add event type whitelist to audit_log (fail-closed write, tolerant read)"
```

---

## Task 3: 两阶段去重（audit_log.py）

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/audit_log.py`
- Create: `plugins/progress-tracker/tests/test_audit_log_dedup.py`

- [ ] **Step 1: 写失败测试**

创建 `plugins/progress-tracker/tests/test_audit_log_dedup.py`：

```python
"""测试两阶段 audit.log 去重。
Pass 1: id 去重（id 相同+内容相同→删副本；id 相同+内容不同→重编号保留两者）
Pass 2: (timestamp+event_type+feature_id) 语义去重
"""
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import audit_log


def r(id_, ts="2026-04-24T12:00:00Z", et="feature_completed", fid=9, **kw):
    rec = {"id": id_, "tx_id": f"TX-{id_}", "timestamp": ts,
           "event_type": et, "feature_id": fid}
    rec.update(kw)
    return rec


class TestPass1IdDedup:
    def test_exact_duplicate_removed(self):
        rec = r("AUDIT-001")
        result = audit_log.deduplicate_audit_log([rec, dict(rec)])
        assert len(result["kept"]) == 1
        assert len(result["removed"]) == 1
        assert result["id_conflicts"] == 0

    def test_id_collision_renumbered_both_kept(self):
        """同 id 但内容不同 → 两条都保留，冲突条被重编号。"""
        r1 = r("AUDIT-001", fid=1)
        r2 = r("AUDIT-001", fid=2)
        result = audit_log.deduplicate_audit_log([r1, r2])
        assert len(result["kept"]) == 2
        ids = {e["id"] for e in result["kept"]}
        assert len(ids) == 2          # 重编号后两个 id 不同
        assert result["id_conflicts"] == 1

    def test_renumbered_record_has_no_leaked_internal_fields(self):
        """重编号后的记录不应注入 _id_conflict_original 等内部字段到数据本身。"""
        r1 = r("AUDIT-001", fid=1)
        r2 = r("AUDIT-001", fid=2)
        result = audit_log.deduplicate_audit_log([r1, r2])
        for rec in result["kept"]:
            assert "_id_conflict_original" not in rec

    def test_id_conflict_metadata_recorded(self):
        """冲突信息应记录在 metadata 字段，供调用者使用。"""
        r1 = r("AUDIT-001", fid=1)
        r2 = r("AUDIT-001", fid=2)
        result = audit_log.deduplicate_audit_log([r1, r2])
        assert len(result["id_conflict_metadata"]) == 1
        meta = result["id_conflict_metadata"][0]
        assert "original_id" in meta
        assert "new_id" in meta

    def test_no_duplicates_unchanged(self):
        recs = [r("AUDIT-001", ts="T1"), r("AUDIT-002", ts="T2")]
        result = audit_log.deduplicate_audit_log(recs)
        assert len(result["kept"]) == 2
        assert result["removed"] == []
        assert result["id_conflicts"] == 0

    def test_nonstandard_id_format_warns_not_crashes(self):
        """非 AUDIT-XXX 格式的 id 不应导致崩溃，应被处理（最大编号不更新）。"""
        recs = [{"id": "CUSTOM-ID", "tx_id": "TX-1",
                 "timestamp": "2026-04-24T12:00:00Z", "event_type": "schema_migration"}]
        result = audit_log.deduplicate_audit_log(recs)
        assert len(result["kept"]) == 1  # 不崩溃，原样保留


class TestPass2SemanticDedup:
    def test_semantic_duplicate_removed(self):
        """相同 (timestamp+event_type+feature_id) 但不同 id → 语义重复，删副本。"""
        ts = "2026-04-24T12:00:00Z"
        result = audit_log.deduplicate_audit_log([
            r("AUDIT-001", ts=ts, fid=9),
            r("AUDIT-002", ts=ts, fid=9),
        ])
        assert len(result["kept"]) == 1
        assert len(result["semantic_duplicates_removed"]) == 1

    def test_global_event_dedup_without_feature_id(self):
        """feature_id 为 None 的全局事件按 (timestamp+event_type) 去重。"""
        ts = "2026-04-24T12:00:00Z"
        g1 = {"id": "AUDIT-001", "tx_id": "TX-1", "timestamp": ts,
              "event_type": "tracker_reset"}
        g2 = {"id": "AUDIT-002", "tx_id": "TX-2", "timestamp": ts,
              "event_type": "tracker_reset"}
        result = audit_log.deduplicate_audit_log([g1, g2])
        assert len(result["kept"]) == 1

    def test_different_features_not_deduped(self):
        """相同 timestamp+event_type 但不同 feature_id → 不是重复。"""
        ts = "2026-04-24T12:00:00Z"
        result = audit_log.deduplicate_audit_log([
            r("AUDIT-001", ts=ts, fid=1),
            r("AUDIT-002", ts=ts, fid=2),
        ])
        assert len(result["kept"]) == 2
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest plugins/progress-tracker/tests/test_audit_log_dedup.py -v 2>&1 | head -20
```

- [ ] **Step 3: 实现 deduplicate_audit_log()**

在 `audit_log.py` 末尾（`clear_audit_log` 之前）添加：

```python
def _record_content_hash(record: Dict[str, Any]) -> str:
    """生成记录内容的哈希键（排除 id 字段）。"""
    content = {k: v for k, v in record.items() if k != "id"}
    return json.dumps(content, sort_keys=True)


def deduplicate_audit_log(
    records: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """两阶段去重审计日志记录。

    Pass 1 — id 去重：
      - same id + same content → 删副本（保留先出现的）
      - same id + diff content → ID 冲突，重编号冲突条（两者都保留）

    Pass 2 — 语义去重：
      - same (timestamp + event_type + feature_id) → 删副本
      - feature_id 缺失时退化为 (timestamp + event_type)

    冲突元数据记录在 id_conflict_metadata 列表，不写入 kept records 本身。

    Returns:
        {
          "kept": [records],
          "removed": [records],
          "semantic_duplicates_removed": [records],
          "id_conflicts": int,
          "id_conflict_metadata": [{"original_id": str, "new_id": str}],
        }
    """
    import copy

    kept_pass1: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    id_conflict_metadata: List[Dict[str, Any]] = []
    id_conflicts = 0

    # 计算最大 AUDIT-XXX 编号，用于重编号冲突条目
    max_id_num = 0
    for record in records:
        rid = record.get("id", "")
        if rid.startswith("AUDIT-"):
            try:
                num = int(rid.split("-")[1])
                max_id_num = max(max_id_num, num)
            except (ValueError, IndexError):
                # 非标准格式，跳过但不崩溃
                pass

    # --- Pass 1: id 去重 ---
    seen_ids: Dict[str, str] = {}  # id → content_hash of first seen

    for record in records:
        rid = record.get("id", "")
        content_hash = _record_content_hash(record)

        if rid not in seen_ids:
            seen_ids[rid] = content_hash
            kept_pass1.append(copy.deepcopy(record))
        else:
            if seen_ids[rid] == content_hash:
                # 完全相同：删副本
                removed.append(record)
            else:
                # ID 冲突：重编号此条，保留两者
                max_id_num += 1
                new_id = f"AUDIT-{max_id_num:03d}"
                new_record = copy.deepcopy(record)
                new_record["id"] = new_id
                kept_pass1.append(new_record)
                id_conflict_metadata.append({
                    "original_id": rid,
                    "new_id": new_id,
                })
                id_conflicts += 1

    # --- Pass 2: 语义去重 ---
    seen_semantic: set = set()
    kept: List[Dict[str, Any]] = []
    semantic_removed: List[Dict[str, Any]] = []

    for record in kept_pass1:
        ts = record.get("timestamp", "")
        et = record.get("event_type", "")
        fid = record.get("feature_id")

        semantic_key = (ts, et, str(fid)) if fid is not None else (ts, et)

        if semantic_key not in seen_semantic:
            seen_semantic.add(semantic_key)
            kept.append(record)
        else:
            semantic_removed.append(record)

    return {
        "kept": kept,
        "removed": removed,
        "semantic_duplicates_removed": semantic_removed,
        "id_conflicts": id_conflicts,
        "id_conflict_metadata": id_conflict_metadata,
    }
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest plugins/progress-tracker/tests/test_audit_log_dedup.py -v
```

- [ ] **Step 5: 提交**

```bash
git add plugins/progress-tracker/hooks/scripts/audit_log.py \
        plugins/progress-tracker/tests/test_audit_log_dedup.py
git commit -m "feat(f0): add two-pass audit.log deduplication (id-based + semantic key)"
```

---

## Task 4: 测试隔离 fixture（conftest.py）

**Files:**
- Modify: `plugins/progress-tracker/tests/conftest.py`

必须先建立测试隔离机制，后续 Task 5/6/7 的测试依赖它。

- [ ] **Step 1: 在 conftest.py 中添加 project_scope fixture**

读取现有 conftest.py：

```bash
head -40 plugins/progress-tracker/tests/conftest.py
```

在文件中（`temp_dir` fixture 之后）添加：

```python
import progress_manager as _pm

@pytest.fixture()
def project_scope(tmp_path, monkeypatch):
    """隔离 progress_manager 和 audit_log 到 tmp_path。

    - 直接设置 _PROJECT_ROOT_OVERRIDE（不走 configure_project_scope 的 git 检查，
      因为 tmp_path 通常在仓库外，会被 resolve_target_project_root 拒绝）
    - 创建 docs/progress-tracker/state/ 目录结构
    - 不设置 PROGRESS_TRACKER_STATE_DIR：核心测试通过 project_root 参数路由
      （只有 audit_log 模块单元测试才用 env var）
    - 测试结束后重置全局状态

    用法：
        def test_foo(project_scope):
            root = project_scope["root"]
            state_dir = project_scope["state_dir"]
            # 通过 audit_log.read_audit_log(project_root=str(root)) 读取
    """
    root = tmp_path
    state_dir = root / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    # 直接注入 project root，绕过 git 检查（tmp_path 可能不在 git repo 内）
    _pm._PROJECT_ROOT_OVERRIDE = root
    _pm._STORAGE_READY_ROOT = None  # 清除路径缓存

    yield {"root": root, "state_dir": state_dir}

    # 测试结束后重置全局状态
    _pm._PROJECT_ROOT_OVERRIDE = None
    _pm._STORAGE_READY_ROOT = None


def _write_progress(state_dir: Path, features: list, current_id=None) -> Path:
    """辅助函数：写 progress.json 到隔离的 state_dir。"""
    import json
    data = {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": features,
        "current_feature_id": current_id,
    }
    path = state_dir / "progress.json"
    path.write_text(json.dumps(data))
    return path


def _write_audit_event(state_dir: Path, event_type: str,
                        feature_id=None, ts="2026-04-24T12:00:00Z",
                        counter=[0]):
    """辅助函数：直接写入 audit 事件（绕过白名单，用于测试数据准备）。
    
    注意：此函数直接写文件，不经过 append_audit_record，用于模拟历史数据
    或在测试中准备不走白名单校验的测试数据。
    """
    import json
    counter[0] += 1
    path = state_dir / "audit.log"
    record = {
        "id": f"AUDIT-{counter[0]:03d}",
        "tx_id": f"TX-{counter[0]:08d}",
        "timestamp": ts,
        "event_type": event_type,
    }
    if feature_id is not None:
        record["feature_id"] = feature_id
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")
```

- [ ] **Step 2: 验证 fixture 可用**

```bash
pytest plugins/progress-tracker/tests/conftest.py --collect-only 2>&1 | head -10
```

无报错即可（conftest.py 不直接运行测试）。

- [ ] **Step 3: 提交**

```bash
git add plugins/progress-tracker/tests/conftest.py
git commit -m "test(f0): add project_scope fixture for progress_manager test isolation"
```

---

## Task 5: 关键命令路径记录状态变更事件

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`

- [ ] **Step 1: 写失败测试**

创建 `plugins/progress-tracker/tests/test_state_event_recording.py`：

```python
"""验证 done/undo/reset 路径向 audit.log 写入对应事件。"""
import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import audit_log
import progress_manager as pm

# 从 conftest 导入辅助函数
sys.path.insert(0, str(Path(__file__).parent))
from conftest import _write_progress, _write_audit_event


class TestRecordFeatureStateEvent:
    def test_function_exists(self):
        assert hasattr(pm, "record_feature_state_event")

    def test_writes_feature_completed_event(self, project_scope):
        root = project_scope["root"]
        pm.record_feature_state_event(
            event_type="feature_completed",
            feature_id=9,
            feature_name="Refactor F9",
        )
        # 必须显式传 project_root，不依赖 PROGRESS_TRACKER_STATE_DIR
        records = audit_log.read_audit_log(ascending=True, project_root=str(root))
        assert len(records) == 1
        r = records[0]
        assert r["event_type"] == "feature_completed"
        assert r["feature_id"] == 9
        assert r["details"]["feature_name"] == "Refactor F9"

    def test_writes_feature_undone_event(self, project_scope):
        root = project_scope["root"]
        pm.record_feature_state_event(
            event_type="feature_undone",
            feature_id=9,
            feature_name="Refactor F9",
        )
        records = audit_log.read_audit_log(ascending=True, project_root=str(root))
        assert records[0]["event_type"] == "feature_undone"

    def test_writes_tracker_reset_without_feature_id(self, project_scope):
        root = project_scope["root"]
        pm.record_feature_state_event(
            event_type="tracker_reset",
            feature_id=None,
            feature_name=None,
        )
        records = audit_log.read_audit_log(ascending=True, project_root=str(root))
        r = records[0]
        assert r["event_type"] == "tracker_reset"
        assert r.get("feature_id") is None

    def test_uses_project_root_from_find_project_root(self, project_scope):
        """audit 事件应写到 project_scope 的 audit.log，不是 audit_log.py 的默认路径。
        
        此测试验证不依赖 PROGRESS_TRACKER_STATE_DIR 时路径路由是否正确。
        """
        pm.record_feature_state_event(
            event_type="feature_completed",
            feature_id=1,
            feature_name="F1",
        )
        # audit.log 应存在于 project_scope 的 state_dir（通过 project_root 路由）
        assert (project_scope["state_dir"] / "audit.log").exists()
        # 再通过显式 project_root 确认可读取
        records = audit_log.read_audit_log(
            ascending=True, project_root=str(project_scope["root"])
        )
        assert len(records) == 1
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest plugins/progress-tracker/tests/test_state_event_recording.py -v 2>&1 | head -20
```

- [ ] **Step 3: 实现 record_feature_state_event()**

在 `progress_manager.py` 中，在 `_append_audit_event()` 函数之后添加：

```python
def record_feature_state_event(
    event_type: str,
    feature_id: Optional[int],
    feature_name: Optional[str],
    extra_details: Optional[Dict[str, Any]] = None,
) -> None:
    """向当前项目的 audit.log 追加特征状态变更事件。

    使用 find_project_root() 确定写入路径，与 progress_manager 的其余路径一致，
    避免跨 plugin 时写入错误的 audit.log。

    Args:
        event_type: 必须在 ALLOWED_EVENT_TYPES 白名单内
        feature_id: 特征 ID（全局事件如 tracker_reset 传 None）
        feature_name: 特征名称（用于可读性，写入 details）
        extra_details: 额外详情（可选）
    """
    if audit_log is None:
        return

    # 使用与 _append_audit_event 相同的 project_root 解析逻辑
    effective_project_root = str(find_project_root())

    try:
        details: Dict[str, Any] = {}
        if feature_name:
            details["feature_name"] = feature_name
        if extra_details:
            details.update(extra_details)

        record: Dict[str, Any] = {
            "id": audit_log.generate_audit_id(project_root=effective_project_root),
            "tx_id": audit_log.generate_tx_id(),
            "timestamp": _iso_now(),
            "event_type": event_type,
        }
        if feature_id is not None:
            record["feature_id"] = feature_id
        if details:
            record["details"] = details

        audit_log.append_audit_record(record, project_root=effective_project_root)
    except ValueError as e:
        # ValueError 来自白名单校验（未知 event_type）—— 这是编程错误，应冒泡
        raise
    except Exception as e:
        # I/O 写失败不能静默吞掉：audit.log 是事实源，写入失败意味着状态不一致
        # 调用方（done/undo/reset）必须感知失败，否则 audit.log 丢事件但命令仍返回成功
        print(f"[audit] ERROR: Failed to record '{event_type}' event: {e}")
        raise
```

- [ ] **Step 4: 在 cmd_done 成功路径插入 feature_completed 事件**

在 `cmd_done()` 中找到特征完成后 `save_progress_json` 的调用区域。使用以下搜索定位插入点：

```bash
grep -n "lifecycle_state.*archived\|development_stage.*completed\|completed.*True" \
  plugins/progress-tracker/hooks/scripts/progress_manager.py | tail -20
```

在特征状态保存完成后（`save_progress_json` 之后），添加：

```python
    # Event sourcing: append feature_completed to audit.log
    # P2 修复：用 resolved_commit（实际 HEAD hash），不用原始 commit_hash 参数
    # 若用户未传 --commit，resolved_commit 是 HEAD；commit_hash 可能是 None 或未解析值
    record_feature_state_event(
        event_type="feature_completed",
        feature_id=feature_id,
        feature_name=feature_name,
        extra_details={"commit_hash": resolved_commit} if resolved_commit else None,
    )
```

- [ ] **Step 5: 在 undo_last_feature 末尾追加 feature_undone 事件**

找到 `undo_last_feature()` 末尾的 `save_progress_json` 调用，之后添加：

```python
    # Event sourcing: append feature_undone to audit.log
    record_feature_state_event(
        event_type="feature_undone",
        feature_id=last_feature.get("id"),
        feature_name=last_feature.get("name"),
    )
```

- [ ] **Step 6: 在 reset_tracking 末尾追加 tracker_reset 事件**

找到 `reset_tracking()` 末尾的 `save_progress_json` 调用，之后添加：

```python
    # Event sourcing: append tracker_reset global event to audit.log
    record_feature_state_event(
        event_type="tracker_reset",
        feature_id=None,
        feature_name=None,
    )
```

- [ ] **Step 7: 运行测试，确认通过**

```bash
pytest plugins/progress-tracker/tests/test_state_event_recording.py -v
```

- [ ] **Step 8: 提交**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_state_event_recording.py
git commit -m "feat(f0): record feature_completed/undone/tracker_reset events in audit.log"
```

---

## Task 6: reconcile-state 命令

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Create: `plugins/progress-tracker/tests/test_reconcile_state.py`

### 核心算法

```
1. 读取 audit.log，两阶段去重
2. _replay_audit_events：
   - 遇到 tracker_reset → 清空已累积状态（reset 是边界）
   - 遇到 feature_completed → 标记为 completed
   - 遇到 feature_undone → 标记为 not_completed
3. 与 progress.json 对比，生成 diff
4. 打印 diff（始终）
5. --check: 返回报告，不修改
6. 否则: 强制写完整一致状态（不用 setdefault）；undo 时清理 completed_at/commit_hash
7. --auto-commit: git commit 动态路径
```

- [ ] **Step 1: 写失败测试**

创建 `plugins/progress-tracker/tests/test_reconcile_state.py`：

```python
"""测试 reconcile-state 命令。"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import audit_log
import progress_manager as pm
sys.path.insert(0, str(Path(__file__).parent))
from conftest import _write_progress, _write_audit_event


class TestNoDrift:
    def test_no_audit_log_returns_no_drift(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 1, "name": "F1", "completed": False}])
        result = pm.cmd_reconcile_state(check_only=True)
        assert result["drift"] is False

    def test_consistent_state_returns_no_drift(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True,
                          "development_stage": "completed",
                          "lifecycle_state": "archived"}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9)
        result = pm.cmd_reconcile_state(check_only=True)
        assert result["drift"] is False


class TestDriftDetection:
    def test_detects_completed_in_audit_not_in_progress(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": False}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9)
        result = pm.cmd_reconcile_state(check_only=True)
        assert result["drift"] is True
        assert 9 in result["drifted_features"]

    def test_detects_undone_in_audit_completed_in_progress(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 5, "name": "F5", "completed": True}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=5, ts="2026-04-24T10:00:00Z")
        _write_audit_event(project_scope["state_dir"],
                           "feature_undone", feature_id=5, ts="2026-04-24T11:00:00Z")
        result = pm.cmd_reconcile_state(check_only=True)
        assert result["drift"] is True
        assert 5 in result["drifted_features"]

    def test_tracker_reset_clears_prior_events_progress_false(self, project_scope):
        """tracker_reset 后无后续事件，progress.json completed=False → 一致（无 drift）。"""
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": False}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9, ts="2026-04-24T10:00:00Z")
        _write_audit_event(project_scope["state_dir"],
                           "tracker_reset", ts="2026-04-24T11:00:00Z")
        # reset 后无后续事件，progress.json completed=False → 与期望一致
        result = pm.cmd_reconcile_state(check_only=True)
        assert result["drift"] is False

    def test_tracker_reset_detects_stale_completed_in_progress(self, project_scope):
        """tracker_reset 后无后续事件，但 progress.json completed=True → drift。
        
        这是 P0 修复的核心场景：reset 后 progress.json 仍残留 completed=True 
        属于数据 drift，必须被检测到。
        """
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True,
                          "development_stage": "completed",
                          "lifecycle_state": "archived"}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9, ts="2026-04-24T10:00:00Z")
        _write_audit_event(project_scope["state_dir"],
                           "tracker_reset", ts="2026-04-24T11:00:00Z")
        result = pm.cmd_reconcile_state(check_only=True)
        assert result["drift"] is True
        assert 9 in result["drifted_features"]


class TestAutoFix:
    def test_auto_fix_sets_complete_state_fields(self, project_scope):
        """completed=True 时强制写完整状态，不用 setdefault。"""
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": False,
                          "development_stage": "developing",
                          "lifecycle_state": "implementing"}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9)
        pm.cmd_reconcile_state(check_only=False)
        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        feat = next(f for f in data["features"] if f["id"] == 9)
        assert feat["completed"] is True
        assert feat["development_stage"] == "completed"   # 强制覆盖，不是 setdefault
        assert feat["lifecycle_state"] == "archived"

    def test_auto_fix_undo_clears_completed_fields(self, project_scope):
        """undone 时清理 completed_at 和 commit_hash。"""
        _write_progress(project_scope["state_dir"],
                        [{"id": 5, "name": "F5", "completed": True,
                          "completed_at": "2026-04-24T00:00:00Z",
                          "commit_hash": "abc1234",
                          "development_stage": "completed"}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_undone", feature_id=5)
        pm.cmd_reconcile_state(check_only=False)
        data = json.loads((project_scope["state_dir"] / "progress.json").read_text())
        feat = next(f for f in data["features"] if f["id"] == 5)
        assert feat["completed"] is False
        assert feat.get("completed_at") is None
        assert feat.get("commit_hash") is None

    def test_no_auto_commit_by_default(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": False}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9)
        with patch("subprocess.run") as mock_run:
            pm.cmd_reconcile_state(check_only=False, auto_commit=False)
            commit_calls = [c for c in mock_run.call_args_list
                            if "commit" in str(c)]
            assert commit_calls == []

    def test_idempotent_second_reconcile_no_drift(self, project_scope):
        """修复后再次运行 reconcile，应报告无 drift。"""
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": False}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9)
        pm.cmd_reconcile_state(check_only=False)
        result2 = pm.cmd_reconcile_state(check_only=True)
        assert result2["drift"] is False
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest plugins/progress-tracker/tests/test_reconcile_state.py -v 2>&1 | head -20
```

- [ ] **Step 3: 实现 _replay_audit_events() 和 cmd_reconcile_state()**

在 `progress_manager.py` 中 `reconcile()` 之后添加：

```python
def _replay_audit_events(
    audit_records: List[Dict[str, Any]],
) -> Tuple[Dict[int, str], bool]:
    """按时间戳升序回放事件，重建每个 feature 的期望完成状态。

    - tracker_reset 是边界：清空已累积状态，reset 之前的事件不再有效
    - feature_completed → "completed"
    - feature_undone → "not_completed"

    Returns:
        (states, last_event_was_reset)
        - states: {feature_id: "completed" | "not_completed"}
        - last_event_was_reset: True 表示 reset 是最后一个边界事件，之后无任何
          feature 状态变更。此时 reconcile 应将所有 completed=True 的 feature 视为 drift。
    """
    relevant_types = {"feature_completed", "feature_undone", "tracker_reset"}
    sorted_records = sorted(
        [r for r in audit_records if r.get("event_type") in relevant_types],
        key=lambda r: r.get("timestamp", ""),
    )

    states: Dict[int, str] = {}
    last_event_was_reset = False
    for record in sorted_records:
        et = record["event_type"]
        if et == "tracker_reset":
            # reset 是边界：清空所有已回放状态
            states.clear()
            last_event_was_reset = True
        elif et == "feature_completed" and record.get("feature_id") is not None:
            states[record["feature_id"]] = "completed"
            last_event_was_reset = False  # reset 后有完成事件，reset 不再是最终边界
        elif et == "feature_undone" and record.get("feature_id") is not None:
            states[record["feature_id"]] = "not_completed"
            last_event_was_reset = False
    return states, last_event_was_reset


def cmd_reconcile_state(
    check_only: bool = False,
    auto_commit: bool = False,
) -> Dict[str, Any]:
    """通过 audit.log 事件回放检测并修复 progress.json 的 drift。

    不接受 project_root 参数：使用 find_project_root() 与其余 progress_manager
    命令保持一致。测试通过 configure_project_scope() 注入。

    Returns:
        {"drift": bool, "drifted_features": [int], "diff": [...],
         "fixed": bool, "committed": bool, "dedup_stats": {...}}
    """
    result: Dict[str, Any] = {
        "drift": False,
        "drifted_features": [],
        "diff": [],
        "fixed": False,
        "committed": False,
        "dedup_stats": {},
    }

    if audit_log is None:
        print("[reconcile-state] audit_log module unavailable")
        return result

    # 1. 读取并去重 audit.log（显式传 project_root，避免跨 plugin 读错）
    effective_root = str(find_project_root())
    raw_records = audit_log.read_audit_log(ascending=True, project_root=effective_root)
    if raw_records:
        dedup = audit_log.deduplicate_audit_log(raw_records)
        records = dedup["kept"]
        result["dedup_stats"] = {
            "original": len(raw_records),
            "kept": len(records),
            "id_conflicts": dedup["id_conflicts"],
            "semantic_dupes": len(dedup["semantic_duplicates_removed"]),
        }
    else:
        records = []

    # 2. 回放事件，重建期望状态
    expected_states, last_event_was_reset = _replay_audit_events(records)

    # 3. 加载 progress.json（必须在 reset boundary 检查前加载）
    data = load_progress_json()
    if not data:
        print("[reconcile-state] No progress.json found")
        return result

    features_map = {f["id"]: f for f in data.get("features", [])}
    diff_items = []

    if not expected_states and not last_event_was_reset:
        print("[reconcile-state] No state-change events in audit.log. Nothing to reconcile.")
        return result

    if last_event_was_reset and not expected_states:
        # tracker_reset 是最后一个事件，之后无任何完成事件
        # → 所有 completed=True 的 feature 均是 drift（reset 后应恢复初始态）
        print("[reconcile-state] Last audit event was tracker_reset with no subsequent completions.")
        print("[reconcile-state] All currently completed features are drift candidates.")
        for feature in data.get("features", []):
            if feature.get("completed", False):
                diff_items.append({
                    "feature_id": feature["id"],
                    "feature_name": feature.get("name", f"Feature {feature['id']}"),
                    "expected_completed": False,
                    "actual_completed": True,
                    "audit_verdict": "not_completed (post-reset boundary)",
                })
    else:
        for fid, expected in expected_states.items():
            feature = features_map.get(fid)
            if feature is None:
                continue
            actual_completed = feature.get("completed", False)
            expected_completed = (expected == "completed")
            if actual_completed != expected_completed:
                diff_items.append({
                    "feature_id": fid,
                    "feature_name": feature.get("name", f"Feature {fid}"),
                    "expected_completed": expected_completed,
                    "actual_completed": actual_completed,
                    "audit_verdict": expected,
                })

    result["drifted_features"] = [d["feature_id"] for d in diff_items]
    result["diff"] = diff_items
    result["drift"] = len(diff_items) > 0

    # 4. 打印 diff（始终）
    if not diff_items:
        print("[reconcile-state] OK — no drift detected")
    else:
        print(f"[reconcile-state] DRIFT DETECTED: {len(diff_items)} feature(s)")
        for item in diff_items:
            print(
                f"  Feature {item['feature_id']} '{item['feature_name']}': "
                f"audit='{item['audit_verdict']}', "
                f"progress.json completed={item['actual_completed']}"
            )

    if check_only or not diff_items:
        return result

    # 5. 修复 progress.json（强制写，不用 setdefault）
    print("[reconcile-state] Fixing progress.json...")
    for item in diff_items:
        feature = features_map.get(item["feature_id"])
        if feature is None:
            continue
        if item["expected_completed"]:
            # 强制写完整完成状态
            feature["completed"] = True
            feature["development_stage"] = "completed"
            feature["lifecycle_state"] = "archived"
        else:
            # 撤销完成：清理完成相关字段
            feature["completed"] = False
            feature["development_stage"] = "developing"
            feature["lifecycle_state"] = "implementing"
            feature.pop("completed_at", None)
            feature.pop("commit_hash", None)

    save_progress_json(data)
    result["fixed"] = True
    print(f"[reconcile-state] Fixed {len(diff_items)} feature(s) in progress.json")
    print("[reconcile-state] NOTE: Not committed. Run 'git commit' manually, or use --auto-commit.")

    # 6. 可选 auto-commit
    if auto_commit:
        try:
            import subprocess
            progress_json_path = get_progress_dir() / PROGRESS_JSON
            try:
                rel_path = str(progress_json_path.relative_to(Path.cwd()))
            except ValueError:
                rel_path = str(progress_json_path)
            commit_msg = (
                f"fix(reconcile): auto-reconcile progress.json [{len(diff_items)} fix(es)] [skip ci]"
            )
            r1 = subprocess.run(
                ["git", "add", rel_path],
                capture_output=True, text=True, timeout=30,
            )
            if r1.returncode == 0:
                r2 = subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    capture_output=True, text=True, timeout=30,
                )
                result["committed"] = r2.returncode == 0
                if result["committed"]:
                    print(f"[reconcile-state] Auto-committed: {commit_msg}")
                else:
                    print(f"[reconcile-state] Auto-commit failed: {r2.stderr.strip()}")
        except Exception as e:
            print(f"[reconcile-state] Auto-commit error: {e}")

    return result
```

- [ ] **Step 4: 注册 reconcile-state 到 CLI**

在 subparsers 区域添加：

```python
    rs_parser = subparsers.add_parser(
        "reconcile-state",
        help="Detect and fix progress.json drift by replaying audit.log events"
    )
    rs_parser.add_argument("--check", action="store_true",
                           help="Detect-only, no file modification")
    rs_parser.add_argument("--auto-commit", action="store_true",
                           help="Auto git-commit after fixing")
```

**不要**将 `"reconcile-state"` 加入 `MUTATING_COMMANDS`。原因：`MUTATING_COMMANDS` 会对整个命令统一加锁并走 route preflight，但 `--check` 是真只读。应在分发层按 `args.check` 分流：

在 args.command 分发区域添加（非 check 模式时手动加锁）：

```python
        if args.command == "reconcile-state":
            check_mode = getattr(args, "check", False)
            if not check_mode:
                # 修复模式走 mutating 保护链路：enforce_route_preflight + progress_transaction
                # 与 MUTATING_COMMANDS 分支（line ~9292-9301）保持一致
                if not enforce_route_preflight("reconcile-state", sys.argv):
                    return 1
                try:
                    with progress_transaction():
                        r = cmd_reconcile_state(
                            check_only=False,
                            auto_commit=getattr(args, "auto_commit", False),
                        )
                except TimeoutError:
                    print("[reconcile-state] ERROR: Could not acquire progress lock")
                    sys.exit(1)
            else:
                r = cmd_reconcile_state(check_only=True)
            # 退出码：修复后 drift 已消除应返回 0；仅检测到 drift 但未修复才返回 1
            # 若 auto-fix 成功（fixed=True），即使最初检测到 drift 也应退出 0
            # 否则 post-merge hook 的 || WARN 会把"修复成功"误报为失败
            if r["fixed"]:
                sys.exit(0)
            else:
                sys.exit(0 if not r["drift"] else 1)
```

- [ ] **Step 5: 运行测试**

```bash
pytest plugins/progress-tracker/tests/test_reconcile_state.py -v
```

- [ ] **Step 6: 手动验证 CLI**

```bash
cd /Users/siunin/Projects/Claude-Plugins
plugins/progress-tracker/prog --project-root plugins/progress-tracker \
  reconcile-state --check
```

- [ ] **Step 7: 提交**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_reconcile_state.py
git commit -m "feat(f0): add reconcile-state command with tracker_reset boundary and complete auto-fix"
```

---

## Task 7: backfill-event 命令（含幂等性保护）

**Files:**
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Create: `plugins/progress-tracker/tests/test_backfill_event.py`

- [ ] **Step 1: 写失败测试**

创建 `plugins/progress-tracker/tests/test_backfill_event.py`：

```python
"""测试 backfill-event 命令。"""
import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import audit_log
import progress_manager as pm
sys.path.insert(0, str(Path(__file__).parent))
from conftest import _write_progress, _write_audit_event


class TestFindBackfillCandidates:
    def test_detects_completed_missing_audit_event(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True,
                          "completed_at": "2026-04-23T02:00:00Z"}])
        candidates = pm.find_backfill_candidates()
        assert 9 in [c["feature_id"] for c in candidates]

    def test_no_candidate_when_event_exists(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True}])
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9)
        candidates = pm.find_backfill_candidates()
        assert candidates == []

    def test_incomplete_feature_not_candidate(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 5, "name": "F5", "completed": False}])
        candidates = pm.find_backfill_candidates()
        assert candidates == []


class TestBackfillEventWrite:
    def test_writes_event_with_backfilled_metadata(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "Refactor F9", "completed": True,
                          "completed_at": "2026-04-23T02:00:00Z"}])
        with patch("builtins.input", return_value="y"):
            result = pm.cmd_backfill_event(feature_id=9)
        assert result["written"] == 1
        records = audit_log.read_audit_log(ascending=True)
        r = records[0]
        assert r["event_type"] == "feature_completed"
        assert r["feature_id"] == 9
        assert r.get("backfilled") is True
        assert "backfill_reason" in r

    def test_idempotent_second_backfill_skipped(self, project_scope):
        """同一 feature 重复 backfill → 第二次检测已有事件，跳过，written=0。"""
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True}])
        with patch("builtins.input", return_value="y"):
            pm.cmd_backfill_event(feature_id=9)
        # 第二次：已有 feature_completed 事件，不再是候选
        with patch("builtins.input", return_value="y"):
            result2 = pm.cmd_backfill_event(feature_id=9)
        assert result2["written"] == 0
        assert result2["candidates"] == 0

    def test_cancelled_on_n(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True}])
        with patch("builtins.input", return_value="n"):
            result = pm.cmd_backfill_event(feature_id=9)
        assert result["written"] == 0
        assert result["cancelled"] is True

    def test_backfill_all_candidates(self, project_scope):
        _write_progress(project_scope["state_dir"],
                        [{"id": 1, "name": "F1", "completed": True},
                         {"id": 9, "name": "F9", "completed": True}])
        with patch("builtins.input", return_value="y"):
            result = pm.cmd_backfill_event(feature_id=None)
        assert result["written"] == 2

    def test_pre_reset_event_does_not_block_post_reset_backfill(self, project_scope):
        """P1 修复：reset 之前的 feature_completed 不阻止 reset 之后的合法 backfill。
        
        场景：F9 在 reset 前已完成（有事件），reset 后 F9 重新变为 completed=True
        但 audit.log 里 reset 后没有新的 feature_completed → 应该是 backfill 候选。
        """
        _write_progress(project_scope["state_dir"],
                        [{"id": 9, "name": "F9", "completed": True,
                          "completed_at": "2026-04-24T12:00:00Z"}])
        # 写 reset 之前的完成事件
        _write_audit_event(project_scope["state_dir"],
                           "feature_completed", feature_id=9, ts="2026-04-24T09:00:00Z")
        # 然后 tracker_reset
        _write_audit_event(project_scope["state_dir"],
                           "tracker_reset", ts="2026-04-24T10:00:00Z")
        # reset 之后没有新的 feature_completed → 仍然是 backfill 候选
        candidates = pm.find_backfill_candidates(feature_id=9)
        assert 9 in [c["feature_id"] for c in candidates], \
            "Pre-reset completion should NOT block post-reset backfill"
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest plugins/progress-tracker/tests/test_backfill_event.py -v 2>&1 | head -20
```

- [ ] **Step 3: 实现 find_backfill_candidates() 和 cmd_backfill_event()**

在 `progress_manager.py` 中 `cmd_reconcile_state` 之后添加：

```python
def find_backfill_candidates(
    feature_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """找出已完成但 audit.log 缺少 feature_completed 事件的 feature。

    幂等性保证：已有 feature_completed（含 backfilled=True 的）也不是候选。

    Returns:
        [{"feature_id": int, "feature_name": str, "completed_at": str}]
    """
    data = load_progress_json()
    if not data:
        return []

    completed_in_audit: set = set()
    if audit_log is not None:
        effective_root = str(find_project_root())
        all_records = audit_log.read_audit_log(ascending=True, project_root=effective_root)

        # 幂等性须考虑 reset 边界：只看最后一次 tracker_reset 之后的 feature_completed
        # reset 之前的完成事件不应阻止 reset 之后合法的 backfill
        last_reset_idx = -1
        for i, r in enumerate(all_records):
            if r.get("event_type") == "tracker_reset":
                last_reset_idx = i

        for r in all_records[last_reset_idx + 1:]:
            if r.get("event_type") == "feature_completed" and r.get("feature_id") is not None:
                completed_in_audit.add(r["feature_id"])

    return [
        {
            "feature_id": f["id"],
            "feature_name": f.get("name", f"Feature {f['id']}"),
            "completed_at": f.get("completed_at", "unknown"),
        }
        for f in data.get("features", [])
        if f.get("completed", False)
        and (feature_id is None or f["id"] == feature_id)
        and f["id"] not in completed_in_audit
    ]


def cmd_backfill_event(
    feature_id: Optional[int] = None,
    yes: bool = False,
) -> Dict[str, Any]:
    """为已完成但缺少 feature_completed 审计事件的 feature 补录事件。

    幂等：已有 feature_completed（含 backfilled）的 feature 不重复写入。
    """
    if audit_log is None:
        print("[backfill-event] audit_log module unavailable")
        return {"written": 0, "candidates": 0, "cancelled": False}

    candidates = find_backfill_candidates(feature_id=feature_id)

    if not candidates:
        print("[backfill-event] No candidates. All completed features have audit events.")
        return {"written": 0, "candidates": 0, "cancelled": False}

    print(f"[backfill-event] {len(candidates)} candidate(s) missing feature_completed events:\n")
    effective_root = str(find_project_root())

    preview_events = []
    for c in candidates:
        ts = c["completed_at"] if c["completed_at"] != "unknown" else _iso_now()
        preview_events.append((c, ts))
        print(f"  Feature {c['feature_id']}: {c['feature_name']}")
        print(f"    → feature_completed  backfilled=true  timestamp={ts}\n")

    if not yes:
        answer = input(
            f"Write {len(preview_events)} backfill event(s) to audit.log? [y/N] "
        ).strip().lower()
        if answer != "y":
            print("[backfill-event] Cancelled.")
            return {"written": 0, "candidates": len(candidates), "cancelled": True}

    written = 0
    for c, ts in preview_events:
        try:
            event = {
                "id": audit_log.generate_audit_id(project_root=effective_root),
                "tx_id": audit_log.generate_tx_id(),
                "timestamp": ts,
                "event_type": "feature_completed",
                "feature_id": c["feature_id"],
                "backfilled": True,
                "backfill_reason": "reconciled from existing progress state",
                "details": {"feature_name": c["feature_name"]},
            }
            audit_log.append_audit_record(event, project_root=effective_root)
            written += 1
            print(f"[backfill-event] Written: F{c['feature_id']} feature_completed")
        except Exception as e:
            print(f"[backfill-event] ERROR: F{c['feature_id']}: {e}")

    print(f"[backfill-event] Done. {written}/{len(candidates)} written.")
    return {"written": written, "candidates": len(candidates), "cancelled": False}
```

- [ ] **Step 4: 注册 CLI 命令**

在 subparsers 区域添加：

```python
    bf_parser = subparsers.add_parser(
        "backfill-event",
        help="Backfill missing feature_completed events for completed features"
    )
    bf_parser.add_argument("--feature-id", type=int, default=None,
                           help="Only backfill this feature ID")
    bf_parser.add_argument("--yes", "-y", action="store_true",
                           help="Skip confirmation prompt")
```

在 `MUTATING_COMMANDS` 中添加 `"backfill-event"`。

分发：

```python
        if args.command == "backfill-event":
            r = cmd_backfill_event(
                feature_id=getattr(args, "feature_id", None),
                yes=getattr(args, "yes", False),
            )
            sys.exit(0 if r["written"] >= 0 else 1)
```

- [ ] **Step 5: 运行测试**

```bash
pytest plugins/progress-tracker/tests/test_backfill_event.py -v
```

- [ ] **Step 6: 提交**

```bash
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_backfill_event.py
git commit -m "feat(f0): add backfill-event command with idempotency protection"
```

---

## Task 8: post-merge hook + install-git-hooks

**Files:**
- Create: `plugins/progress-tracker/hooks/scripts/post_merge_hook.sh`
- Modify: `plugins/progress-tracker/hooks/scripts/progress_manager.py`
- Create: `plugins/progress-tracker/tests/test_git_hooks_install.py`

- [ ] **Step 1: 创建 post-merge hook 脚本**

```bash
cat > /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/hooks/scripts/post_merge_hook.sh << 'HOOKEOF'
#!/usr/bin/env bash
# post-merge Git hook: auto-reconcile progress.json after merge
# Install via: prog install-git-hooks
# 覆盖所有受影响 plugin（包括 standalone root），不仅限于 plugins/progress-tracker。

set -euo pipefail

CHANGED=$(git diff ORIG_HEAD --name-only 2>/dev/null \
  | grep -E "audit\.log|progress\.json" || true)

if [ -z "$CHANGED" ]; then
  exit 0
fi

echo "[post-merge] Progress state files changed. Running reconcile-state..."

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PROG="$REPO_ROOT/plugins/progress-tracker/prog"

if [ ! -x "$PROG" ]; then
  echo "[post-merge] WARN: prog not found at $PROG, skipping"
  exit 0
fi

# 1. 提取所有受影响的 plugin 目录（plugins/<name>）并逐个 reconcile
PLUGINS=$(echo "$CHANGED" | grep -oE "^plugins/[^/]+" | sort -u || true)

for PLUGIN_PATH in $PLUGINS; do
  PLUGIN_ROOT="$REPO_ROOT/$PLUGIN_PATH"
  echo "[post-merge] Reconciling $PLUGIN_PATH..."
  # 使用绝对路径 PLUGIN_ROOT，不依赖 cwd（hook 执行目录可能不是 repo root）
  "$PROG" --project-root "$PLUGIN_ROOT" \
    reconcile-state --auto-commit || {
    echo "[post-merge] WARN: reconcile-state for $PLUGIN_PATH exited $?. Review manually."
    # 不阻断 merge，继续处理其他 plugin
  }
done

# 2. 处理 standalone root tracker（非 plugins/ 子目录）
STANDALONE=$(echo "$CHANGED" | grep -E "^docs/progress-tracker" || true)
if [ -n "$STANDALONE" ]; then
  echo "[post-merge] Reconciling standalone root tracker..."
  "$PROG" --project-root "$REPO_ROOT" \
    reconcile-state --auto-commit || {
    echo "[post-merge] WARN: reconcile-state for root exited $?. Review manually."
  }
fi
HOOKEOF
chmod +x /Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/hooks/scripts/post_merge_hook.sh
```

- [ ] **Step 2: 写安装测试**

创建 `plugins/progress-tracker/tests/test_git_hooks_install.py`：

```python
"""测试 install-git-hooks 命令。

注意：实现使用 `git rev-parse --git-path hooks`（支持 worktree 的 .git 文件）。
测试必须 mock subprocess.run 使其返回 hooks 目录路径，而不是依赖真实 git repo。
"""
import stat
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import progress_manager as pm


def _make_git_rev_parse_mock(hooks_dir: Path):
    """创建 subprocess.run mock，对 --git-path hooks 返回指定目录。"""
    def mock_run(cmd, **kwargs):
        if "--git-path" in cmd and "hooks" in cmd:
            m = MagicMock()
            m.returncode = 0
            m.stdout = str(hooks_dir) + "\n"
            return m
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        return m
    return mock_run


class TestInstallGitHooks:
    def _setup_hooks_dir(self, tmp_path):
        """创建 hooks 目录（可以是 .git/hooks 或 worktree 的 hooks 路径）。"""
        git_hooks = tmp_path / ".git" / "hooks"
        git_hooks.mkdir(parents=True)
        return git_hooks

    def test_creates_post_merge_hook(self, tmp_path):
        git_hooks = self._setup_hooks_dir(tmp_path)
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            result = pm.cmd_install_git_hooks()
        assert (git_hooks / "post-merge").exists()
        assert result["installed"] is True

    def test_hook_is_executable(self, tmp_path):
        git_hooks = self._setup_hooks_dir(tmp_path)
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            pm.cmd_install_git_hooks()
        hook = git_hooks / "post-merge"
        assert hook.stat().st_mode & stat.S_IXUSR

    def test_hook_content_contains_reconcile_state(self, tmp_path):
        git_hooks = self._setup_hooks_dir(tmp_path)
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            pm.cmd_install_git_hooks()
        content = (git_hooks / "post-merge").read_text()
        assert "reconcile-state" in content

    def test_git_command_failure_returns_error(self, tmp_path):
        """git rev-parse 失败时返回 installed=False。"""
        def mock_git_fail(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 128
            m.stderr = "not a git repository"
            return m

        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=mock_git_fail):
            result = pm.cmd_install_git_hooks()
        assert result["installed"] is False
        assert result.get("error")

    def test_overwrites_existing_hook(self, tmp_path):
        git_hooks = self._setup_hooks_dir(tmp_path)
        (git_hooks / "post-merge").write_text("#!/bin/bash\necho old_hook")
        with patch("progress_manager.find_project_root", return_value=tmp_path), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(git_hooks)):
            result = pm.cmd_install_git_hooks()
        assert result["installed"] is True
        assert "reconcile-state" in (git_hooks / "post-merge").read_text()

    def test_worktree_git_file_scenario(self, tmp_path):
        """P1 修复验证：worktree 下 .git 是文件，hooks 在不同路径。
        
        通过 mock git rev-parse 返回 worktree hooks 路径，模拟 worktree 场景。
        """
        # worktree 的 hooks 指向主 repo 的 hooks
        worktree_hooks = tmp_path / "main_repo" / ".git" / "hooks"
        worktree_hooks.mkdir(parents=True)
        # .git 是文件（模拟 worktree）
        git_file = tmp_path / "worktree" / ".git"
        git_file.parent.mkdir(parents=True)
        git_file.write_text(f"gitdir: {tmp_path}/main_repo/.git/worktrees/wt1\n")

        with patch("progress_manager.find_project_root", return_value=tmp_path / "worktree"), \
             patch("subprocess.run", side_effect=_make_git_rev_parse_mock(worktree_hooks)):
            result = pm.cmd_install_git_hooks()
        assert result["installed"] is True
        assert (worktree_hooks / "post-merge").exists()
```

- [ ] **Step 3: 运行，确认失败**

```bash
pytest plugins/progress-tracker/tests/test_git_hooks_install.py -v 2>&1 | head -20
```

- [ ] **Step 4: 实现 cmd_install_git_hooks()**

```python
def cmd_install_git_hooks() -> Dict[str, Any]:
    """将 post-merge hook 安装到当前项目的 git hooks 目录。

    使用 `git rev-parse --git-path hooks` 获取 hooks 路径，
    正确支持 worktree（.git 是文件而非目录的场景）。
    """
    import stat
    import subprocess

    repo_root = find_project_root()

    # 通过 git 查询 hooks 路径：worktree 下 .git 是文件，不是目录
    # git rev-parse --git-path hooks 在两种情况下均返回正确路径
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            capture_output=True, text=True, timeout=10,
            cwd=str(repo_root),
        )
        if result.returncode != 0:
            msg = f"git rev-parse --git-path hooks failed: {result.stderr.strip()}"
            print(f"[install-git-hooks] ERROR: {msg}")
            return {"installed": False, "hook_path": None, "error": msg}

        hooks_path = result.stdout.strip()
        git_hooks_dir = Path(hooks_path)
        if not git_hooks_dir.is_absolute():
            git_hooks_dir = repo_root / git_hooks_dir
        git_hooks_dir.mkdir(exist_ok=True, parents=True)
    except FileNotFoundError:
        msg = "git not found in PATH"
        print(f"[install-git-hooks] ERROR: {msg}")
        return {"installed": False, "hook_path": None, "error": msg}
    except Exception as e:
        msg = f"Failed to resolve git hooks directory: {e}"
        print(f"[install-git-hooks] ERROR: {msg}")
        return {"installed": False, "hook_path": None, "error": msg}

    source = Path(__file__).parent / "post_merge_hook.sh"
    if not source.exists():
        msg = f"Hook source not found: {source}"
        print(f"[install-git-hooks] ERROR: {msg}")
        return {"installed": False, "hook_path": None, "error": msg}

    target = git_hooks_dir / "post-merge"
    target.write_text(source.read_text())
    current_mode = target.stat().st_mode
    target.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"[install-git-hooks] Installed: {target}")
    return {"installed": True, "hook_path": str(target), "error": None}
```

- [ ] **Step 5: 注册 CLI**

```python
    subparsers.add_parser("install-git-hooks",
                          help="Install post-merge hook for auto reconcile-state")
```

分发（无需 MUTATING lock，只修改 .git/hooks）：

```python
        if args.command == "install-git-hooks":
            r = cmd_install_git_hooks()
            sys.exit(0 if r["installed"] else 1)
```

- [ ] **Step 6: 运行测试**

```bash
pytest plugins/progress-tracker/tests/test_git_hooks_install.py -v
```

- [ ] **Step 7: 提交**

```bash
git add plugins/progress-tracker/hooks/scripts/post_merge_hook.sh \
        plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_git_hooks_install.py
git commit -m "feat(f0): add post-merge hook and install-git-hooks command"
```

---

## Task 9: Feature 9 状态恢复（实操验证）

- [ ] **Step 1: 检查 reconcile-state 当前状态**

```bash
plugins/progress-tracker/prog --project-root plugins/progress-tracker reconcile-state --check
```

- [ ] **Step 2: 运行 backfill-event，补录 F9**

```bash
plugins/progress-tracker/prog --project-root plugins/progress-tracker backfill-event --feature-id 9
```

输入 `y` 确认。

- [ ] **Step 3: 验证 audit.log 写入正确**

```bash
tail -3 plugins/progress-tracker/docs/progress-tracker/state/audit.log
```

期望：最新行含 `"event_type":"feature_completed","feature_id":9,"backfilled":true`

- [ ] **Step 4: 再次 reconcile --check，确认无 drift**

```bash
plugins/progress-tracker/prog --project-root plugins/progress-tracker reconcile-state --check
```

期望：`OK — no drift detected`

- [ ] **Step 5: 提交**

```bash
git add plugins/progress-tracker/docs/progress-tracker/state/audit.log
git commit -m "fix(f0): backfill feature_completed event for Feature 9 via backfill-event"
```

---

## Task 10: 集成测试 & 验收

- [ ] **Step 1: 运行所有 F0 测试**

```bash
pytest plugins/progress-tracker/tests/test_audit_log_whitelist.py \
       plugins/progress-tracker/tests/test_audit_log_dedup.py \
       plugins/progress-tracker/tests/test_state_event_recording.py \
       plugins/progress-tracker/tests/test_reconcile_state.py \
       plugins/progress-tracker/tests/test_backfill_event.py \
       plugins/progress-tracker/tests/test_git_hooks_install.py \
       -v --tb=short 2>&1 | tail -25
```

期望：全部 passed

- [ ] **Step 2: 验证 .gitattributes 覆盖两个 plugin**

```bash
git check-attr merge plugins/progress-tracker/docs/progress-tracker/state/audit.log
git check-attr merge plugins/note-organizer/docs/progress-tracker/state/audit.log
```

期望：两行均 `merge: union`

- [ ] **Step 3: 全量回归测试**

```bash
pytest plugins/progress-tracker/tests/ -q --tb=short 2>&1 | tail -20
```

期望：无新增失败

- [ ] **Step 4: 安装 post-merge hook**

```bash
plugins/progress-tracker/prog --project-root plugins/progress-tracker install-git-hooks
# 使用 git rev-parse 验证（兼容 worktree，不硬编码 .git/hooks）
ls -la "$(git rev-parse --git-path hooks)/post-merge"
```

- [ ] **Step 5: 提交最终验收**

```bash
git add -p
git commit -m "test(f0): integration validation — all acceptance criteria verified"
```

---

## Task 11: plan_path 归一化（CLI 入口层修复）

（此 Task 来自计划的第二轮补充，已在文件中存在，保留不变。）

---

## 验收标准对照

| 验收场景 | 验证命令 | Task |
|---------|---------|------|
| audit.log union merge 覆盖所有 plugin | `git check-attr merge plugins/*/docs/.../audit.log` | 1 |
| 未知 event_type 写入时被拒绝 | `test_audit_log_whitelist.py` | 2 |
| 现有生产事件（set_finish_state 等）不受影响 | `test_audit_log_whitelist.py::test_set_finish_state_allowed` | 2 |
| 两阶段去重正确处理 ID 冲突和语义重复 | `test_audit_log_dedup.py` | 3 |
| done/undo/reset 写入对应 audit 事件 | `test_state_event_recording.py` | 5 |
| tracker_reset 是 replay 边界 | `test_reconcile_state.py::test_tracker_reset_clears_prior_events` | 6 |
| reconcile 强制写完整状态，undo 清理 completed_at | `test_reconcile_state.py::TestAutoFix` | 6 |
| backfill-event 幂等（第二次不重复写入） | `test_backfill_event.py::test_idempotent_second_backfill_skipped` | 7 |
| post-merge hook 安装正确且可执行 | `test_git_hooks_install.py` | 8 |
| Feature 9 通过 backfill-event 恢复 | Task 9 手动验证 | 9 |
