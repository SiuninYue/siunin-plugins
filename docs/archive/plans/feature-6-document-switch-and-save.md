# Feature 6: Document Switching And Save

## Context

Implement document switching and save UX in the Progress UI so users can:
- browse available markdown documents,
- switch active document from the left panel,
- see explicit save feedback after checkbox changes,
- refresh document list manually.

## Tasks

1. Verify document list and switching flow
- Ensure `/api/files` list is rendered in left panel.
- Ensure clicking a document triggers `loadFile(path)` and updates active document metadata.

2. Normalize save feedback wording
- During checkbox status write, show `保存中...`.
- After successful write and reload, show `已保存`.
- Keep conflict/error feedback unchanged.

3. Verify manual refresh flow
- Refresh button triggers `loadFiles(true)`.
- `Ctrl+R` / `Cmd+R` triggers `loadFiles(true)` and prevents browser hard refresh.

4. Add regression tests for frontend behavior
- Assert save wording exists in frontend script.
- Assert refresh controls and document switching hooks are present.

## Acceptance Mapping

- Feature step 1 (文档列表显示可切换文档): Covered by task 1 and `test_frontend_has_document_list_refresh_and_switch_hooks`.
- Feature step 2 (点击文档名称切换右侧内容): Covered by task 1 and `test_frontend_has_document_list_refresh_and_switch_hooks`.
- Feature step 3 (修改状态后显示“保存中...”然后“已保存”): Covered by task 2 and `test_frontend_uses_chinese_save_status_messages`.
- Feature step 4 (刷新按钮或 Ctrl+R 重新加载文档): Covered by task 3 and `test_frontend_has_document_list_refresh_and_switch_hooks`.

## Risks

- Frontend string assertions can be brittle if copy changes frequently.
- Keyboard shortcut behavior is validated at script level, not full browser E2E.
- Existing unrelated workspace changes may coexist; avoid touching unrelated files.
