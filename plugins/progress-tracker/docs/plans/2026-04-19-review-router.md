# Review Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `hooks/scripts/review_router.py`，根据 feature 的 change_categories 计算所需 review lanes（eng/qa/docs 强制，design/devex 可选，docs-only 短路），并集成到 `set_current()` 初始化和 `cmd_done()` 门控。

**Architecture:**
- `review_router.py` 是无副作用纯函数模块（类比 `evaluator_gate.py`）。`pending` 字段**不作为 gate 依据**——`get_pending_lanes()` 恒从 `required - passed` 计算（SSOT）。
- gate 串行顺序：evaluator gate（`status == "pass"`）→ review gate（`get_pending_lanes() == []`）。evaluator `required_reviews` 状态是阻断项，开发者完成人工评审后需重跑 evaluator 产出 `pass`，再进入 review gate。
- `cmd_done()` 的 review gate 使用 `get_pending_lanes(feat)` 计算（`required - passed`），不依赖存储的 `pending` 字段，防止脏数据绕过。
- categories 推断结果首次落盘到 `change_spec.categories`，防止后续名称变更导致漂移。
- 开发者通过 `prog review-pass --feature-id <id> --lane <lane>` 命令标记 lane 通过，解除 return 7 阻断。`review-pass` 注册在 `MUTATING_COMMANDS` 中，走 `progress_transaction()` 锁和 `enforce_route_preflight` 链路。

**两套机制的语义边界（硬约束，禁止混淆）：**
- `evaluator_gate.status = "required_reviews"` ≠ F-11 review lanes。前者由 `_is_security_defect()` 触发，表示"发现安全/严重缺陷，需修复后重新评估"——是**缺陷修复流程**（fix → re-evaluate → `pass`）。
- F-11 review lanes 是**预规划的质量里程碑**，由 `change_spec.categories` 决定，与 evaluator 输出无关。
- 实现中**不得**将 `evaluator.status = "required_reviews"` 自动转换为 review lane 赋值。如有此需求，属于单独 feature。

**Tech Stack:** Python 3.12+, pytest, 已有 `hooks/scripts/` 模块体系，`quality_gates.reviews` schema（required/passed/pending 三字段）

---

## Gate Flow（明确串行顺序，解决 P0）

```
/prog done
  │
  ├─ [Gate 1] evaluator.status == "pass"?
  │     ├─ "retry"           → return 6 (evaluator 发现 blocking defect)
  │     ├─ "required_reviews" → return 6 (evaluator 要求人工评审；
  │     │                        开发者完成评审后需重跑 evaluator 产出 pass)
  │     └─ "pass"            → 继续
  │
  ├─ [Gate 2] get_pending_lanes(feat) == []?
  │     ├─ 非空              → return 7 (review lanes 未全部通过)
  │     └─ 空                → 继续
  │
  └─ complete_feature(...)
```

> **两套机制互不干扰**：evaluator 的 `required_reviews` 状态要求修复缺陷并重跑 evaluator（不是完成 review lanes）。review lanes 是独立的预规划质量门，由 `change_spec.categories` 决定，不由 evaluator 触发。
>
> **UX 解阻路径**：review lane 完成后 → `prog review-pass --feature-id <id> --lane <lane>` → 全部 lane 通过 + evaluator 已 `pass` → `/prog done` 放行。

---

## File Map

| 状态 | 路径 | 职责 |
|------|------|------|
| CREATE | `hooks/scripts/review_router.py` | 核心模块：categories 推断 + 落盘 + lane 计算 + 持久化 API |
| CREATE | `tests/test_review_router.py` | 契约测试：覆盖全部公开 API + 边界 + 退出码 |
| MODIFY | `hooks/scripts/progress_manager.py` | `set_current()` 集成 + `cmd_done()` review gate + `prog review-pass` 命令 |

---

## 2026-04-21 审查后修订（P1/P2 补丁）

- [x] **P1 修订：`cmd_done()` 对空 reviews fail-closed**  
  当 `quality_gates.reviews.required == []` 时，先执行 `initialize_reviews()` 再做 gate 判定；若仍有 pending lanes，`return 7` 阻断。  
  目标：防止历史/异常数据因未初始化 reviews 绕过 F-11 gate。

- [x] **P1 修订：移除不存在命令指引**  
  scope creep 场景不再引用 `prog review-add-lane`（该命令不在本 feature 范围内）。  
  改为：手动变更 `quality_gates.reviews.required/passed/pending`（或后续独立 feature 提供显式命令）。

- [x] **P2 修订：关键词推断改词边界匹配**  
  禁止 `if keyword in text` 子串匹配，改为正则词边界匹配，避免 `api` 命中 `capability` 等误判。

- [x] **P2 修订：补 `cmd_review_pass()` 行为测试**  
  补齐成功路径与错误码路径（feature 不存在、required 为空、lane 非 required）。

---

## Task 1: 创建 review_router.py 骨架与 _LANE_RULES 映射表

**Files:**
- Create: `hooks/scripts/review_router.py`
- Create: `tests/test_review_router.py`

- [ ] **Step 1.1: 写失败测试——验证模块可导入且 _LANE_RULES 存在**

新建 `tests/test_review_router.py`：

```python
#!/usr/bin/env python3
"""review_router contract tests (F-11)."""

import pytest
from review_router import _LANE_RULES, required_reviews, initialize_reviews, mark_review_passed, get_pending_lanes


def test_lane_rules_defines_backend():
    assert "backend" in _LANE_RULES
    assert {"eng", "qa", "docs"}.issubset(_LANE_RULES["backend"])


def test_lane_rules_frontend_includes_design():
    assert "design" in _LANE_RULES.get("frontend", set())


def test_lane_rules_sdk_includes_devex():
    assert "devex" in _LANE_RULES.get("sdk", set())


def test_lane_rules_docs_only_has_docs():
    assert _LANE_RULES.get("docs") == {"docs"}
```

- [ ] **Step 1.2: 运行测试，确认失败**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/test_review_router.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError`（review_router 不存在）

- [ ] **Step 1.3: 创建 review_router.py 骨架**

创建 `hooks/scripts/review_router.py`：

```python
#!/usr/bin/env python3
"""Review lane router (F-11).

Determines which review lanes are required for a feature based on its
change_categories, then persists the result into quality_gates.reviews.

Lane types:
  Required (always): eng, qa, docs
  Optional (by category): design (frontend/ui), devex (sdk/api/cli)
  Short-circuit: docs-only category -> ["docs"] only, bypasses fail-closed

Gate contract:
  cmd_done uses get_pending_lanes() — computed as required - passed.
  The stored `pending` field is a display cache only; never use it for gate decisions.

Public API:
  required_reviews(feature) -> list[str]
  initialize_reviews(feature) -> None          # idempotent; writes quality_gates.reviews
  mark_review_passed(feature, lane: str) -> None
  get_pending_lanes(feature) -> list[str]      # canonical gate source: required - passed
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

# ---------------------------------------------------------------------------
# Lane rules: category -> set of required lanes
# ---------------------------------------------------------------------------
_LANE_RULES: Dict[str, Set[str]] = {
    "backend":  {"eng", "qa", "docs"},
    "frontend": {"eng", "qa", "docs", "design"},
    "ui":       {"eng", "qa", "docs", "design"},
    "sdk":      {"eng", "qa", "docs", "devex"},
    "api":      {"eng", "qa", "docs", "devex"},
    "cli":      {"eng", "qa", "docs", "devex"},
    "docs":     {"docs"},
    "schema":   {"eng", "qa", "docs"},
    "security": {"eng", "qa", "docs"},
    "infra":    {"eng", "qa", "docs"},
}

_ALWAYS_REQUIRED: Set[str] = {"eng", "qa", "docs"}

# Keywords → category for inference fallback
_KEYWORD_MAP: Dict[str, str] = {
    "frontend":  "frontend",
    "ui":        "ui",
    "sdk":       "sdk",
    "api":       "api",
    "cli":       "cli",
    "docs":      "docs",
    "readme":    "docs",
    "schema":    "schema",
    "security":  "security",
    "infra":     "infra",
    "backend":   "backend",
}
```

- [ ] **Step 1.4: 运行测试，确认通过**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/test_review_router.py -v
```

Expected: 4 passed

- [ ] **Step 1.5: Commit**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
git add plugins/progress-tracker/hooks/scripts/review_router.py \
        plugins/progress-tracker/tests/test_review_router.py
git commit -m "feat(f11): add review_router skeleton with _LANE_RULES mapping"
```

---

## Task 2: 实现 required_reviews() — categories 推断、持久化、docs-only 短路

**Files:**
- Modify: `hooks/scripts/review_router.py`
- Modify: `tests/test_review_router.py`

- [ ] **Step 2.1: 写失败测试**

在 `tests/test_review_router.py` 末尾追加：

```python
# --- required_reviews() ---

def _make_feature(name: str = "test feature", categories=None, in_scope=None, description: str = "") -> dict:
    return {
        "id": 99,
        "name": name,
        "description": description,
        "change_spec": {
            "why": "test",
            "in_scope": in_scope or [],
            "out_of_scope": [],
            "risks": [],
            **({"categories": categories} if categories is not None else {}),
        },
    }


def test_required_reviews_explicit_categories_backend():
    feat = _make_feature(categories=["backend"])
    lanes = required_reviews(feat)
    assert set(lanes) == {"eng", "qa", "docs"}


def test_required_reviews_explicit_categories_frontend_adds_design():
    feat = _make_feature(categories=["frontend"])
    lanes = required_reviews(feat)
    assert "design" in lanes
    assert {"eng", "qa", "docs"}.issubset(set(lanes))


def test_required_reviews_explicit_categories_sdk_adds_devex():
    feat = _make_feature(categories=["sdk"])
    lanes = required_reviews(feat)
    assert "devex" in lanes
    assert {"eng", "qa", "docs"}.issubset(set(lanes))


def test_required_reviews_docs_only_short_circuits():
    """docs-only must NOT trigger fail-closed eng/qa/docs (AI-a opt 5)."""
    feat = _make_feature(categories=["docs"])
    lanes = required_reviews(feat)
    assert set(lanes) == {"docs"}, f"Expected only docs, got {lanes}"
    assert "eng" not in lanes
    assert "qa" not in lanes


def test_required_reviews_multiple_categories_union():
    feat = _make_feature(categories=["frontend", "sdk"])
    lanes = required_reviews(feat)
    assert {"eng", "qa", "docs", "design", "devex"}.issubset(set(lanes))


def test_required_reviews_keyword_inference_fallback_frontend():
    """Inference scans name + description + in_scope (AI-a opt 3)."""
    feat = _make_feature(name="落地 frontend 组件")
    lanes = required_reviews(feat)
    assert "design" in lanes


def test_required_reviews_keyword_inference_from_description():
    feat = _make_feature(name="some feature", description="update api endpoint logic")
    lanes = required_reviews(feat)
    assert "devex" in lanes


def test_required_reviews_keyword_inference_from_in_scope():
    feat = _make_feature(name="misc update", in_scope=["sdk handler refactor"])
    lanes = required_reviews(feat)
    assert "devex" in lanes


def test_required_reviews_fail_closed_unknown_category():
    feat = _make_feature(categories=["totally_unknown_xyz"])
    lanes = required_reviews(feat)
    assert set(lanes) >= {"eng", "qa", "docs"}


def test_required_reviews_no_categories_defaults_to_always_required():
    feat = _make_feature()
    lanes = required_reviews(feat)
    assert set(lanes) >= {"eng", "qa", "docs"}


def test_required_reviews_design_not_in_backend():
    feat = _make_feature(categories=["backend"])
    lanes = required_reviews(feat)
    assert "design" not in lanes


def test_required_reviews_devex_not_in_backend():
    feat = _make_feature(categories=["backend"])
    lanes = required_reviews(feat)
    assert "devex" not in lanes


def test_required_reviews_inference_persists_to_change_spec(tmp_path):
    """First-time inference writes result to change_spec.categories (AI-b P1: prevent drift)."""
    feat = _make_feature(name="update api handler")
    required_reviews(feat, persist=True)
    assert feat["change_spec"].get("categories") is not None
    assert "api" in feat["change_spec"]["categories"]


def test_required_reviews_explicit_categories_not_overwritten(tmp_path):
    """Explicit categories are never overwritten by inference (AI-b P1)."""
    feat = _make_feature(categories=["backend"])
    required_reviews(feat, persist=True)
    assert feat["change_spec"]["categories"] == ["backend"]


def test_required_reviews_persist_idempotent_no_json_drift():
    """Calling required_reviews(persist=True) twice must not change categories (AI-b supplement test 2).
    
    Prevents JSON churn: repeated calls must be stable.
    """
    feat = _make_feature(name="update api handler")
    lanes1 = required_reviews(feat, persist=True)
    cats_after_first = list(feat["change_spec"].get("categories", []))

    lanes2 = required_reviews(feat, persist=True)  # second call: categories already set
    cats_after_second = list(feat["change_spec"].get("categories", []))

    assert lanes1 == lanes2, "Repeated calls must return identical lanes"
    assert cats_after_first == cats_after_second, "categories must not change on second persist call"


def test_required_reviews_mixed_docs_and_backend_does_not_short_circuit():
    """docs + backend mixed categories must NOT trigger docs-only short-circuit (AI-b supplement test 3).
    
    Short-circuit only applies when ALL categories are 'docs'.
    """
    feat = _make_feature(categories=["docs", "backend"])
    lanes = required_reviews(feat)
    # Should have full eng/qa/docs, not just docs
    assert set(lanes) >= {"eng", "qa", "docs"}
    assert "eng" in lanes
    assert "docs" in lanes
```

- [ ] **Step 2.2: 运行测试，确认失败**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/test_review_router.py -k "required_reviews" -v 2>&1 | tail -20
```

Expected: `ImportError` / `TypeError`（`required_reviews` 未实现）

- [ ] **Step 2.3: 实现 required_reviews()**

在 `hooks/scripts/review_router.py` 中，`_KEYWORD_MAP` 定义之后追加：

```python
# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _infer_categories_from_text(feature: Dict[str, Any]) -> List[str]:
    """Infer categories from feature name, description, and in_scope text.

    Scans all three sources (AI-a opt 3: broader inference coverage).
    """
    text = " ".join([
        feature.get("name", ""),
        feature.get("description", ""),
        *feature.get("change_spec", {}).get("in_scope", []),
    ]).lower()
    found: Set[str] = set()
    for keyword, category in _KEYWORD_MAP.items():
        if re.search(rf"(?<![a-z0-9_]){re.escape(keyword)}(?![a-z0-9_])", text):
            found.add(category)
    return sorted(found)


def required_reviews(feature: Dict[str, Any], persist: bool = False) -> List[str]:
    """Return sorted list of required review lane IDs for the given feature.

    Source priority:
      1. feature.change_spec.categories (explicit — used as-is)
      2. keyword inference from name + description + change_spec.in_scope
      3. fail-closed: always include eng, qa, docs (except docs-only short-circuit)

    docs-only short-circuit: if the only categories are ["docs"], return ["docs"]
    without applying fail-closed eng/qa/docs (AI-a opt 5).

    persist=True: write inferred categories back to change_spec.categories
    (only when categories were absent — never overwrites explicit values).
    """
    change_spec = feature.setdefault("change_spec", {})
    categories: List[str] = change_spec.get("categories") or []

    inferred = False
    if not categories:
        categories = _infer_categories_from_text(feature)
        inferred = True

    # Persist inferred categories to prevent future drift (AI-b P1)
    if persist and inferred and categories and not change_spec.get("categories"):
        change_spec["categories"] = categories

    # docs-only short-circuit: pure documentation change must not trigger eng/qa gate
    if categories and all(c == "docs" for c in categories):
        return ["docs"]

    lanes: Set[str] = set(_ALWAYS_REQUIRED)
    for cat in categories:
        extra = _LANE_RULES.get(cat)
        if extra:
            lanes.update(extra)
        # unknown category: fail-closed (already have _ALWAYS_REQUIRED)

    return sorted(lanes)
```

- [ ] **Step 2.4: 运行测试，确认通过**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/test_review_router.py -k "required_reviews" -v
```

Expected: 全部 required_reviews 测试通过

- [ ] **Step 2.5: Commit**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
git add plugins/progress-tracker/hooks/scripts/review_router.py \
        plugins/progress-tracker/tests/test_review_router.py
git commit -m "feat(f11): implement required_reviews() with docs-only short-circuit, inference persistence"
```

---

## Task 3: 实现 initialize_reviews()、mark_review_passed()、get_pending_lanes()

**Files:**
- Modify: `hooks/scripts/review_router.py`
- Modify: `tests/test_review_router.py`

**SSOT 契约（解决 AI-a opt 1 + AI-b P1）：**
- `pending` 字段保留在 JSON schema 中（向后兼容），但仅作展示缓存
- `get_pending_lanes()` 始终从 `required - passed` 计算（gate 决策必须用此函数）
- `mark_review_passed()` 只追加 `passed`，不写 `pending`
- `initialize_reviews()` 写入 `required` 和初始 `passed=[]`，pending 字段留空（由展示层按需填充）

- [ ] **Step 3.1: 写失败测试**

在 `tests/test_review_router.py` 末尾追加：

```python
# --- initialize_reviews() ---

def test_initialize_reviews_writes_required_and_empty_passed():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    reviews = feat["quality_gates"]["reviews"]
    assert set(reviews["required"]) == {"eng", "qa", "docs"}
    assert reviews["passed"] == []


def test_initialize_reviews_idempotent_does_not_overwrite_passed():
    """SSOT: second call must not reset already-passed lanes (AI-b P1)."""
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    feat["quality_gates"]["reviews"]["passed"].append("eng")
    initialize_reviews(feat)  # second call
    reviews = feat["quality_gates"]["reviews"]
    assert "eng" in reviews["passed"]


def test_initialize_reviews_creates_quality_gates_if_absent():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    assert "quality_gates" in feat
    assert "reviews" in feat["quality_gates"]


def test_initialize_reviews_frontend_includes_design():
    feat = _make_feature(categories=["frontend"])
    initialize_reviews(feat)
    reviews = feat["quality_gates"]["reviews"]
    assert "design" in reviews["required"]


def test_initialize_reviews_scope_creep_does_not_auto_update():
    """Idempotency vs scope creep: mid-dev change_spec changes do NOT auto-update lanes.
    
    This is intentional behavior — manual intervention required to change required lanes.
    (AI-a opt 4: document this explicitly as tested contract)
    """
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    assert "design" not in feat["quality_gates"]["reviews"]["required"]

    # Simulate mid-development scope creep: developer adds "frontend" to categories
    feat["change_spec"]["categories"] = ["backend", "frontend"]
    initialize_reviews(feat)  # second call — already initialized, must NOT add "design"

    assert "design" not in feat["quality_gates"]["reviews"]["required"], (
        "initialize_reviews() is idempotent: scope changes after first init "
        "do NOT auto-expand required lanes. Manual update to reviews payload is required."
    )


# --- mark_review_passed() ---

def test_mark_review_passed_appends_to_passed():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    mark_review_passed(feat, "eng")
    reviews = feat["quality_gates"]["reviews"]
    assert "eng" in reviews["passed"]


def test_mark_review_passed_idempotent_on_double_pass():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    mark_review_passed(feat, "eng")
    mark_review_passed(feat, "eng")
    reviews = feat["quality_gates"]["reviews"]
    assert reviews["passed"].count("eng") == 1


def test_mark_review_passed_ignores_unknown_lane():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    mark_review_passed(feat, "nonexistent_lane")
    reviews = feat["quality_gates"]["reviews"]
    assert "nonexistent_lane" not in reviews["passed"]


# --- get_pending_lanes() — SSOT: always required - passed ---

def test_get_pending_lanes_returns_required_minus_passed():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    mark_review_passed(feat, "eng")
    pending = get_pending_lanes(feat)
    assert "eng" not in pending
    assert "qa" in pending
    assert "docs" in pending


def test_get_pending_lanes_empty_when_all_passed():
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    for lane in ["eng", "qa", "docs"]:
        mark_review_passed(feat, lane)
    assert get_pending_lanes(feat) == []


def test_get_pending_lanes_returns_empty_when_reviews_not_initialized():
    feat = _make_feature()
    assert get_pending_lanes(feat) == []


def test_get_pending_lanes_ignores_stored_pending_field():
    """SSOT: gate must use required - passed, not the stored pending field (AI-b P1)."""
    feat = _make_feature(categories=["backend"])
    initialize_reviews(feat)
    mark_review_passed(feat, "eng")
    # Manually corrupt the stored pending field (simulates dirty data)
    feat["quality_gates"]["reviews"]["pending"] = []  # dirty: says nothing pending
    # get_pending_lanes must still detect qa and docs as pending
    pending = get_pending_lanes(feat)
    assert "qa" in pending
    assert "docs" in pending


def test_get_pending_lanes_detects_partial_passed_with_empty_pending_field():
    """AI-b P1: required=[eng,qa,docs], passed=[eng], pending=[] (corrupt) -> still detects [qa,docs]."""
    feat = _make_feature(categories=["backend"])
    feat.setdefault("quality_gates", {})["reviews"] = {
        "required": ["eng", "qa", "docs"],
        "passed": ["eng"],
        "pending": [],  # corrupt/stale cache
    }
    pending = get_pending_lanes(feat)
    assert set(pending) == {"qa", "docs"}
```

- [ ] **Step 3.2: 运行测试，确认失败**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/test_review_router.py \
  -k "initialize_reviews or mark_review_passed or get_pending_lanes" -v 2>&1 | tail -20
```

Expected: `ImportError`

- [ ] **Step 3.3: 实现三个 API**

在 `hooks/scripts/review_router.py` 中，`required_reviews()` 之后追加：

```python
def initialize_reviews(feature: Dict[str, Any]) -> None:
    """Populate quality_gates.reviews.required with computed lanes.

    Idempotent: if quality_gates.reviews.required is already non-empty,
    this function does nothing — preserves in-progress review state.

    SSOT note: does NOT write pending field. get_pending_lanes() computes
    required - passed at gate-check time.

    Scope creep note: mid-development change_spec changes do NOT auto-update
    required lanes after first initialization. Manual intervention required.
    """
    feature.setdefault("quality_gates", {})
    reviews = feature["quality_gates"].setdefault(
        "reviews", {"required": [], "passed": [], "pending": []}
    )
    reviews.setdefault("required", [])
    reviews.setdefault("passed", [])
    reviews.setdefault("pending", [])

    if reviews["required"]:
        # Already initialized — idempotent: do not overwrite.
        return

    lanes = required_reviews(feature, persist=True)
    reviews["required"] = lanes
    # passed starts empty; pending field left as display cache (not written here)


def mark_review_passed(feature: Dict[str, Any], lane: str) -> None:
    """Record that a review lane has been completed.

    SSOT: only appends to passed[]. Does NOT touch pending[] — pending is a
    display cache recomputed by get_pending_lanes().
    Idempotent: calling twice has no additional effect.
    Unknown lanes (not in required) are silently ignored.
    """
    reviews = feature.get("quality_gates", {}).get("reviews", {})
    required: List[str] = reviews.get("required", [])
    if lane not in required:
        return

    passed: List[str] = reviews.setdefault("passed", [])
    if lane not in passed:
        passed.append(lane)


def get_pending_lanes(feature: Dict[str, Any]) -> List[str]:
    """Return canonical pending lanes: required minus passed.

    ALWAYS recomputes from required and passed — never reads the stored pending
    field. This prevents dirty-data bypass at the cmd_done gate (AI-b P1).
    Returns [] if reviews not initialized (safe default for gate checks).
    """
    reviews = feature.get("quality_gates", {}).get("reviews", {})
    required: List[str] = reviews.get("required", [])
    passed: List[str] = reviews.get("passed", [])
    return [lane for lane in required if lane not in passed]
```

- [ ] **Step 3.4: 运行全部 review_router 测试**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/test_review_router.py -v
```

Expected: 全部通过

- [ ] **Step 3.5: Commit**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
git add plugins/progress-tracker/hooks/scripts/review_router.py \
        plugins/progress-tracker/tests/test_review_router.py
git commit -m "feat(f11): implement initialize_reviews/mark_review_passed/get_pending_lanes with SSOT contract"
```

---

## Task 4: 在 set_current() 中集成 initialize_reviews() + 新增 prog review-pass 命令

**Files:**
- Modify: `hooks/scripts/progress_manager.py`
- Modify: `tests/test_review_router.py`

**解决 AI-a opt 2（UX 闭环）+ P1-2（MUTATING_COMMANDS 护栏）**：
- `review-pass` 必须加入 `MUTATING_COMMANDS`，走 `progress_transaction()` 锁和 `enforce_route_preflight` 链路
- 必须在 `subparsers` 中注册（不得在函数内 inline argparse，否则绕过主 dispatch 护栏）
- 必须在 `_dispatch_command()` 内派发（与 `set-finish-state` 相同模式）

- [ ] **Step 4.1: 写失败测试——set_current 触发 initialize_reviews**

在 `tests/test_review_router.py` 末尾追加：

```python
# --- progress_manager integration: set_current initializes reviews ---

import sys
import json
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).parent.parent / "hooks" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import progress_manager


def _make_progress_json_with_feature(tmp_path: Path, categories=None) -> Path:
    """Write minimal progress.json with one pending feature."""
    feature = {
        "id": 42,
        "name": "test feature for review router integration",
        "description": "",
        "completed": False,
        "deferred": False,
        "lifecycle_state": "approved",
        "development_stage": "planning",
        "change_spec": {
            "why": "test",
            "in_scope": ["test"],
            "out_of_scope": [],
            "risks": [],
            **({"categories": categories} if categories is not None else {}),
        },
        "requirement_ids": ["REQ-042"],
        "acceptance_scenarios": ["Scenario: passes"],
        "quality_gates": {
            "evaluator": {"status": "pending", "score": None, "defects": [], "last_run_at": None, "evaluator_model": None},
            "reviews": {"required": [], "passed": [], "pending": []},
            "ship_check": {"status": "pending", "failures": [], "last_run_at": None},
        },
        "sprint_contract": {"scope": "", "done_criteria": [], "test_plan": [], "accepted_by": None, "accepted_at": None},
        "handoff": {"from_phase": None, "to_phase": None, "artifact_path": None, "created_at": None},
    }
    data = {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": [feature],
        "current_feature_id": None,
        "updates": [],
        "retrospectives": [],
        "runtime_context": {},
        "linked_projects": [],
        "linked_snapshot": {},
        "tracker_role": "standalone",
        "project_code": None,
        "routing_queue": [],
        "active_routes": [],
        "bugs": [],
        "current_bug_id": None,
    }
    state_dir = tmp_path / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "progress.json").write_text(json.dumps(data))
    return tmp_path


def test_review_pass_is_in_mutating_commands():
    """P1-2: review-pass must be in MUTATING_COMMANDS to get transaction lock + preflight (AI-b P1-2)."""
    assert "review-pass" in progress_manager.MUTATING_COMMANDS


def test_set_current_initializes_reviews_when_empty(tmp_path):
    proj_root = _make_progress_json_with_feature(tmp_path, categories=["backend"])
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        progress_manager.set_current(42)

    data = json.loads((proj_root / "docs/progress-tracker/state/progress.json").read_text())
    feat = next(f for f in data["features"] if f["id"] == 42)
    reviews = feat["quality_gates"]["reviews"]
    assert set(reviews["required"]) == {"eng", "qa", "docs"}
    assert reviews["passed"] == []


def test_set_current_does_not_reset_existing_reviews(tmp_path):
    proj_root = _make_progress_json_with_feature(tmp_path, categories=["backend"])
    progress_file = proj_root / "docs/progress-tracker/state/progress.json"
    data = json.loads(progress_file.read_text())
    feat = next(f for f in data["features"] if f["id"] == 42)
    feat["quality_gates"]["reviews"] = {
        "required": ["eng", "qa", "docs"],
        "passed": ["eng"],
        "pending": ["qa", "docs"],
    }
    progress_file.write_text(json.dumps(data))

    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        progress_manager.set_current(42)

    data2 = json.loads(progress_file.read_text())
    feat2 = next(f for f in data2["features"] if f["id"] == 42)
    reviews2 = feat2["quality_gates"]["reviews"]
    assert "eng" in reviews2["passed"]
    assert "eng" not in reviews2.get("pending", [])
```

- [ ] **Step 4.2: 运行测试，确认失败**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/test_review_router.py \
  -k "test_set_current" -v 2>&1 | tail -20
```

Expected: FAIL

- [ ] **Step 4.3: 在 progress_manager.py 的 import 区域添加 review_router 导入**

找到这段代码（搜索 `EVALUATOR_GATE_AVAILABLE`）：
```python
try:
    from evaluator_gate import assess as _evaluator_assess, EvaluatorResult as _EvaluatorResult
    EVALUATOR_GATE_AVAILABLE = True
except ImportError:
    EVALUATOR_GATE_AVAILABLE = False
```

在其正后方追加：
```python
try:
    from review_router import (
        initialize_reviews as _initialize_reviews,
        get_pending_lanes as _get_pending_lanes,
        mark_review_passed as _mark_review_passed,
    )
    REVIEW_ROUTER_AVAILABLE = True
except ImportError:
    REVIEW_ROUTER_AVAILABLE = False
```

- [ ] **Step 4.4: 在 set_current() 中集成 initialize_reviews()**

在 `set_current()` 函数内，`_update_runtime_context(data, source="set_current")` 调用之前插入：

```python
    # F-11: initialize review lanes when starting a new feature (idempotent)
    if not feature.get("completed", False) and REVIEW_ROUTER_AVAILABLE:
        _initialize_reviews(feature)
```

- [ ] **Step 4.5: 新增 cmd_review_pass() 函数 + MUTATING_COMMANDS 注册 + subparser + dispatch**

**4.5-A: 添加 `"review-pass"` 到 MUTATING_COMMANDS（约 line 169）**

找到 `MUTATING_COMMANDS = {` 集合定义，在 `"reconcile-evaluator",` 之后追加：

```python
    "review-pass",
```

**4.5-B: 实现 `cmd_review_pass()` 函数（在 `cmd_set_finish_state` 之后添加）**

```python
def cmd_review_pass(feature_id: int, lane: str) -> int:
    """Mark a review lane as passed for the given feature (F-11).

    Registered in MUTATING_COMMANDS — runs inside progress_transaction() lock.
    CLI usage: prog review-pass --feature-id <id> --lane <lane>

    Exit codes:
      0 — lane marked passed
      1 — no tracking / review_router unavailable
      3 — feature not found
      4 — feature has no required review lanes (not initialized)
      5 — lane not in required lanes
    """
    if not REVIEW_ROUTER_AVAILABLE:
        print("[REVIEW] review_router not available", file=sys.stderr)
        return 1

    data = load_progress_json()
    if not data:
        print("[REVIEW] No progress tracking found", file=sys.stderr)
        return 1

    features = data.get("features", [])
    feature = next((f for f in features if f.get("id") == feature_id), None)
    if feature is None:
        print(f"[REVIEW] Feature {feature_id} not found", file=sys.stderr)
        return 3

    reviews = feature.get("quality_gates", {}).get("reviews", {})
    required = reviews.get("required", [])
    if not required:
        print(f"[REVIEW] Feature {feature_id} has no required review lanes", file=sys.stderr)
        return 4

    if lane not in required:
        print(
            f"[REVIEW] Lane '{lane}' is not in required lanes {required}",
            file=sys.stderr,
        )
        return 5

    _mark_review_passed(feature, lane)
    pending = _get_pending_lanes(feature)

    save_progress_json(data)
    save_progress_md(generate_progress_md(data))

    print(f"[REVIEW] Lane '{lane}' marked passed for feature {feature_id}")
    if pending:
        print(f"[REVIEW] Remaining pending: {pending}")
    else:
        print("[REVIEW] All required lanes passed. /prog done will no longer be blocked by review gate.")
    return 0
```

**4.5-C: 在 `main()` 的 `subparsers` 注册 `review-pass`（在 `set_finish_state_parser` 之后）**

```python
    review_pass_parser = subparsers.add_parser(
        "review-pass",
        help="Mark a review lane as passed for the current feature (F-11)",
    )
    review_pass_parser.add_argument(
        "--feature-id",
        type=int,
        required=True,
        help="Feature ID",
    )
    review_pass_parser.add_argument(
        "--lane",
        required=True,
        help="Review lane to mark passed (eng, qa, docs, design, devex)",
    )
```

**4.5-D: 在 `_dispatch_command()` 中添加 dispatch 分支（在 `set-finish-state` 分支之后）**

```python
        if args.command == "review-pass":
            return cmd_review_pass(args.feature_id, args.lane)
```

注意：`review-pass` 在 `MUTATING_COMMANDS` 中，所以主 dispatch 流程自动为其加 `progress_transaction()` 锁（见 `main()` 约 line 8740 的 `with progress_transaction():` 块）。不需要在 `cmd_review_pass` 内部加锁。

- [ ] **Step 4.6: 运行集成测试**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/test_review_router.py \
  -k "test_set_current" -v
```

Expected: 2 passed

- [ ] **Step 4.7: 验证 prog review-pass CLI 可调用，且在 MUTATING_COMMANDS 中**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 plugins/progress-tracker/hooks/scripts/progress_manager.py review-pass --help 2>&1 | head -5
```

Expected: 显示 `--feature-id` 和 `--lane` 参数

```bash
python3 -c "import sys; sys.path.insert(0, 'plugins/progress-tracker/hooks/scripts'); import progress_manager; assert 'review-pass' in progress_manager.MUTATING_COMMANDS, 'NOT in MUTATING_COMMANDS'; print('OK: review-pass is in MUTATING_COMMANDS')"
```

Expected: `OK: review-pass is in MUTATING_COMMANDS`

- [ ] **Step 4.8: 运行全量测试确认无回归**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/ -q --tb=short 2>&1 | tail -10
```

Expected: 全部通过（0 failed）

- [ ] **Step 4.9: Commit**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_review_router.py
git commit -m "feat(f11): integrate initialize_reviews into set_current(); add prog review-pass command"
```

---

## Task 5: 在 cmd_done() 中添加 review gate 检查（SSOT + 退出码测试）

**Files:**
- Modify: `hooks/scripts/progress_manager.py`
- Modify: `tests/test_review_router.py`

**Gate 实现要点（解决 AI-b P0/P1/P2）：**
- Gate 使用 `_get_pending_lanes(feat)`（`required - passed`），不读 `pending` 字段
- 串行位置：evaluator gate（return 6）通过后，review gate（return 7）
- 补充 return 7 的三个退出码测试

- [ ] **Step 5.1: 写失败测试——退出码测试（AI-b P2）**

在 `tests/test_review_router.py` 末尾追加：

```python
# --- cmd_done review gate: exit code tests (AI-b P2) ---

def _make_progress_with_execution_complete(tmp_path: Path, reviews: dict) -> Path:
    """Write progress.json with feature in execution_complete phase."""
    feature = {
        "id": 55,
        "name": "feature for done gate test",
        "description": "",
        "completed": False,
        "deferred": False,
        "lifecycle_state": "implementing",
        "development_stage": "developing",
        "change_spec": {"why": "test", "in_scope": [], "out_of_scope": [], "risks": []},
        "requirement_ids": ["REQ-055"],
        "acceptance_scenarios": [],
        "integration_status": None,
        "quality_gates": {
            "evaluator": {
                "status": "pass", "score": 100, "defects": [],
                "last_run_at": "2026-01-01T00:00:00Z", "evaluator_model": None,
            },
            "reviews": reviews,
            "ship_check": {"status": "pending", "failures": [], "last_run_at": None},
        },
        "sprint_contract": {"scope": "", "done_criteria": [], "test_plan": [], "accepted_by": None, "accepted_at": None},
        "handoff": {"from_phase": None, "to_phase": None, "artifact_path": None, "created_at": None},
    }
    data = {
        "schema_version": "2.1",
        "project_name": "test",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "features": [feature],
        "current_feature_id": 55,
        "updates": [],
        "retrospectives": [],
        "runtime_context": {},
        "linked_projects": [],
        "linked_snapshot": {},
        "tracker_role": "standalone",
        "project_code": None,
        "routing_queue": [],
        "active_routes": [],
        "bugs": [],
        "current_bug_id": None,
        "workflow_state": {"phase": "execution_complete"},
    }
    state_dir = tmp_path / "docs" / "progress-tracker" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "progress.json").write_text(json.dumps(data))
    return tmp_path


def test_cmd_done_returns_7_when_required_lanes_pending(tmp_path):
    """AI-b P2 test 1: required=[eng,qa,docs], passed=[eng] -> return 7."""
    reviews = {"required": ["eng", "qa", "docs"], "passed": ["eng"], "pending": ["qa", "docs"]}
    proj_root = _make_progress_with_execution_complete(tmp_path, reviews)
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        rc = progress_manager.cmd_done()
    assert rc == 7, f"Expected 7 (review gate), got {rc}"


def test_cmd_done_not_blocked_when_all_lanes_passed(tmp_path):
    """AI-b P2 test 2: required=[eng,qa,docs], passed=[eng,qa,docs] -> review gate passes (rc != 7)."""
    reviews = {"required": ["eng", "qa", "docs"], "passed": ["eng", "qa", "docs"], "pending": []}
    proj_root = _make_progress_with_execution_complete(tmp_path, reviews)
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        rc = progress_manager.cmd_done()
    assert rc != 7, f"Review gate must not block when all lanes passed (got rc={rc})"


def test_cmd_done_returns_7_when_pending_field_corrupt_but_passed_incomplete(tmp_path):
    """AI-b P1+P2 test 3: required=[eng,qa,docs], passed=[eng], pending=[] (dirty) -> return 7.
    
    Gate uses required - passed (SSOT), not stored pending field.
    """
    reviews = {
        "required": ["eng", "qa", "docs"],
        "passed": ["eng"],
        "pending": [],  # corrupt/stale cache
    }
    proj_root = _make_progress_with_execution_complete(tmp_path, reviews)
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        rc = progress_manager.cmd_done()
    assert rc == 7, f"Gate must detect pending lanes via required-passed, not stored pending field (got {rc})"


def test_cmd_done_returns_7_when_no_reviews_configured(tmp_path, capsys):
    """Empty required lanes: cmd_done must initialize reviews then block with return 7."""
    reviews = {"required": [], "passed": [], "pending": []}
    proj_root = _make_progress_with_execution_complete(tmp_path, reviews)
    with patch.object(progress_manager, "_PROJECT_ROOT_OVERRIDE", proj_root):
        rc = progress_manager.cmd_done()
    assert rc == 7
```

- [ ] **Step 5.2: 运行测试，确认失败**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/test_review_router.py \
  -k "test_cmd_done" -v 2>&1 | tail -20
```

Expected: `test_cmd_done_returns_7_when_required_lanes_pending` 和 `test_cmd_done_returns_7_when_pending_field_corrupt` FAIL

- [ ] **Step 5.3: 在 cmd_done() 中插入 review gate**

在 `hooks/scripts/progress_manager.py` 的 `cmd_done()` 中，找到 evaluator gate 的末尾（`return 6` 语句后，仍在 `if gate_feat is not None:` block 内）：

当前代码结构（约 5976 行）：
```python
    if refreshed_for_gate:
        gate_feat = next(...)
        if gate_feat is not None:
            evaluator_payload = gate_feat.get("quality_gates", {}).get("evaluator", {})
            eval_status = evaluator_payload.get("status")
            if eval_status != "pass":
                print(...)
                return 6
            # <-- 在此处插入 review gate
```

插入内容：
```python
            # F-11: review gate (Gate 2, after evaluator gate)
            # Uses get_pending_lanes() — computed as required - passed (SSOT, not pending field)
            if REVIEW_ROUTER_AVAILABLE:
                pending_lanes = _get_pending_lanes(gate_feat)
                if pending_lanes:
                    print(
                        f"[DONE] BLOCKED: pending reviews: {pending_lanes}. "
                        "Run: prog review-pass --feature-id <id> --lane <lane>",
                        file=sys.stderr,
                    )
                    return 7
```

- [ ] **Step 5.4: 运行退出码测试**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/test_review_router.py \
  -k "test_cmd_done" -v
```

Expected: 4 passed

- [ ] **Step 5.5: 运行验收测试**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/test_review_router.py -v 2>&1 | tail -30
```

Expected: 全部通过

- [ ] **Step 5.6: 运行全量回归测试**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
python3 -m pytest plugins/progress-tracker/tests/ -q --tb=short 2>&1 | tail -10
```

Expected: 全部通过（0 failed）

- [ ] **Step 5.7: Commit**

```bash
cd /Users/siunin/Projects/Claude-Plugins/.worktrees/feature/f11-review-router
git add plugins/progress-tracker/hooks/scripts/progress_manager.py \
        plugins/progress-tracker/tests/test_review_router.py
git commit -m "feat(f11): add review gate to cmd_done() with SSOT check and return code 7"
```

---

## Self-Review

## Acceptance Mapping

- `review_router.py` 新增并提供 `required_reviews / initialize_reviews / mark_review_passed / get_pending_lanes`。
- `set_current()` 集成 `initialize_reviews()`，确保 feature 启动时初始化 lane。
- `cmd_done()` 在 evaluator gate 后执行 review gate；空 `required` 先初始化再判定，pending 则 `return 7`。
- `prog review-pass` 提供解除 review gate 的 CLI 出口，并注册到 `MUTATING_COMMANDS`。
- 测试覆盖关键词推断、docs-only、SSOT 计算、空 `required` 自愈阻断、`cmd_review_pass()` 退出码契约。

## Risks

- 历史数据中 `change_spec` 信息不足会导致 fail-closed（`eng/qa/docs`），可能增加人工通过成本。
- 关键词推断为启发式规则，虽已改为词边界匹配，仍可能存在语义误判；需结合后续真实样本调整词表。
- scope creep 后 `required` 不自动扩展是有意契约，若流程期望自动扩展需单独 feature 设计与迁移。

### Spec coverage

| 验收标准 | 对应 Task |
|---------|----------|
| 新增 hooks/scripts/review_router.py | Task 1 |
| 按 change categories 计算 required/pending/passed | Task 2-3 |
| pytest test_review_router.py 通过 | Task 1-5 |
| design/devex 可选（仅特定 category） | Task 2（test_required_reviews_design_not_in_backend，devex_not_in_backend） |
| eng/qa/docs 按规则强制 | Task 2（fail-closed，no_categories_defaults） |
| docs-only 短路 | Task 2（test_required_reviews_docs_only_short_circuits） |
| set_current() 集成 | Task 4 |
| /prog done review gate return 7 | Task 5 |
| CLI 解除阻断出口 | Task 4（prog review-pass） |
| SSOT：gate 用 required-passed，不读 pending 字段 | Task 3（test_get_pending_lanes_ignores_stored_pending_field）+ Task 5（test_cmd_done_returns_7_when_pending_field_corrupt） |
| 推断落盘防漂移 | Task 2（test_required_reviews_inference_persists_to_change_spec） |
| 幂等+scope creep 行为文档化 | Task 3（test_initialize_reviews_scope_creep_does_not_auto_update） |
| Gate 串行顺序（evaluator→review）文档化 | Architecture 章节 Gate Flow 图 |
| return 7 三个退出码测试 | Task 5（test 1/2/3） |
| evaluator `required_reviews` ≠ review lanes（语义边界硬约束）| Architecture 章节"两套机制的语义边界" |
| review-pass 注册 MUTATING_COMMANDS + 走 transaction 锁 | Task 4（4.5-A + test_review_pass_is_in_mutating_commands）|
| persist 幂等无 JSON 抖动 | Task 2（test_required_reviews_persist_idempotent_no_json_drift）|
| docs+backend 混合不误短路 | Task 2（test_required_reviews_mixed_docs_and_backend_does_not_short_circuit）|

### Placeholder scan

无 TBD/TODO/placeholder。

### Type consistency

- `required_reviews(feature, persist=False)` → `List[str]`：Task 2 定义，Task 3/4 调用一致
- `initialize_reviews(feature)` → `None`：Task 3 定义，Task 4 集成
- `mark_review_passed(feature, lane: str)` → `None`：Task 3 定义，Task 4 CLI 调用
- `get_pending_lanes(feature)` → `List[str]`：Task 3 定义，Task 5 gate 调用，测试引用一致
- `cmd_review_pass(feature_id: int, lane: str)` → `int`：Task 4 定义，CLI 路由调用
- `_LANE_RULES: Dict[str, Set[str]]`：Task 1 定义，Task 2 使用一致
