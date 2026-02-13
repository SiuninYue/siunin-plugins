# Feature 5 Plan: Six-State Checkbox Rendering

## Tasks

1. Replace plain-text editor rendering with line-by-line rendering that detects markdown checkbox lines (`- [ ]`, `- [/]`, `- [x]`, `- [-]`, `- [!]`, `- [?]`).
2. Add checkbox interaction handlers:
   - Left click cycles the primary loop (`☐ -> 🔄 -> ☑ -> ☐`).
   - Right click opens a six-state context menu.
   - Keyboard shortcuts `1-6` map to the six checkbox states for the selected checkbox.
3. Wire checkbox changes to `PATCH /api/checkbox` with optimistic concurrency fields (`base_rev`, `base_mtime`) and reload content on save.
4. Add regression tests that assert six-state metadata, menu wiring, keyboard mapping, and PATCH usage are present in the UI source.

## Acceptance Mapping

- `测试 checkbox 渲染: 打开页面检查是否显示 ☐🔄☑➖❌❓ 六种状态`
  Mapped to Task 1 and Task 2 (status icon metadata + checkbox renderer).
- `验证状态切换: 点击 checkbox 应按 ☐->🔄->☑ 主循环切换`
  Mapped to Task 2 (primary cycle function + click handler).
- `测试右键菜单: 右键点击 checkbox 应显示 6 状态选项`
  Mapped to Task 2 (context menu UI and bindings).
- `检查快捷键: 按 1-6 键应切换对应状态`
  Mapped to Task 2 (keyboard map and save trigger).

## Risks

- Line index mapping drift between frontend split logic and backend `splitlines(keepends=True)` could patch the wrong line.
  Mitigation: normalize newline handling to emulate Python behavior and use original rendered line index.
- Save conflicts may occur under concurrent edits and surface as poor UX.
  Mitigation: detect `409` and show an explicit conflict status.
- Context menu placement can overflow viewport on small screens.
  Mitigation: clamp menu position to viewport bounds.
