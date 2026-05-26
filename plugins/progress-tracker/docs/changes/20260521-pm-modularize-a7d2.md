# Change: progress_manager.py 深度模块化拆分

- **ID**: 20260521-pm-modularize-a7d2
- **Date**: 2026-05-21
- **Component**: progress_manager
- **Summary**: 拆分 progress_manager.py 为 7 个子模块（Method A，零测试改动）
- **Root Cause**: 13,587 行单文件导致 AI session 无法全量读取，影响高风险修复定位
- **Fixes**: F18

## 变更细节
我们将 `progress_manager.py` 的大部分具体逻辑提取到了以下子模块：
- `lock_manager.py`
- `state_io.py`
- `git_utils.py`
- `worktree_handler.py`
- `route_sync.py`
- `route_commands.py`
- `evaluator_gateway.py`

在主入口 `progress_manager.py` 中，采用**薄 Wrapper + 参数注入**的方式实现向上兼容的 shim 转发，维持所有测试中对 `progress_manager.X` 符号的 Mock 机制有效性，无需改动任何测试文件。
