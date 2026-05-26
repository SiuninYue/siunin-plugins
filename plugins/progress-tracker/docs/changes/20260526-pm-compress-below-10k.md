# Change: progress_manager.py 进阶压缩至 10,000 行以下

- **ID**: 20260526-pm-compress-below-10k
- **Date**: 2026-05-26
- **Component**: progress_manager
- **Summary**: 进一步提取文档生成、缺陷追踪、工作区校验等模块至 doc_generator.py 和 bug_tracker.py，使 progress_manager.py 跌破 10,000 行。
- **Root Cause**: 满足 F18 阶段将 progress_manager.py 瘦身至 ≤10,000 行的红线要求。
- **Fixes**: F18

## 变更细节
我们继续提取了 `progress_manager.py` 内部的逻辑，并保持 Method A 零测试改动的兼容性：
- 提取 `validate_plan_document`、`generate_direct_tdd_note`、`generate_progress_md` 和 `archive_feature_docs` 至新模块 `doc_generator.py`。
- 提取 `_add_bug_internal`、`add_bug`、`update_bug`、`list_bugs` 至新模块 `bug_tracker.py`。
- 提取 `check_worktree_branch_consistency` 至已有子模块 `worktree_handler.py`。
- 在 `progress_manager.py` 中为以上所有函数建立薄 Wrapper 桥接转发，并正确绑定了 `is_wrapper = True`，从而完美兼容所有的 Mock 机制，测试文件完全零修改。
