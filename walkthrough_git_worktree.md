# 修复 worktree 状态分裂问题 - Walkthrough

我们已经审查并执行了 `~/.claude/plans/glowing-snacking-sunbeam.md` 所列出的“最强大脑审查计划”，完成了所有功能修复，并完成了以下四项高优先级修正，确保 git worktree 能够完美共享状态而不导致分裂，并具有零误判和强并发保障。

## 修改内容

我们修改了 [progress_manager.py](file:///Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/hooks/scripts/progress_manager.py)，主要做了以下改动：

1. **引入与优化 Helper 函数**：
   - `_get_main_repo_root()`：检测当前项目路径是否处于 worktree 下。**已升级为严格模式**：只接受类似 `.../.git/worktrees/<name>` 的连续 `.git` 和 `worktrees` 目录结构，以防止误判普通路径。
   - `_resolve_main_repo_path()`：将 worktree 中的具体项目子目录路径，映射为对应的、存在于主仓库中的等效路径。
2. **并发锁安全与强一致性双写（P1/P2 修正）**：
   - 重构了锁机制，使 `_progress_lock_path`、`_acquire_progress_lock`、`_release_progress_lock` 和 `progress_transaction` 支持通过 `project_root` 参数，管理多个不同根目录的重入锁。
   - 使 `_save_progress_payload_at_root()` 内部默认由 `progress_transaction(project_root=project_root)` 守护，确保所有跨 root 写入都自带统一锁保护，彻底杜绝并发覆盖风险。
   - 在 `_store_evaluator_result()` 中，将主仓的读-改-写行为用 `with progress_transaction(project_root=main_root)` 统一包裹起来，防止跨 root 发生“先读旧数据，后覆盖新数据”的并发丢更新漏洞。
   - **[新] 强一致性双写优化**：将本地的 `save_progress_json(data)` 本地副本写入挪入了 `main_root` 锁的作用域内部，并紧贴主仓写入（两步原子写入 `os.replace` 连贯执行），将系统崩溃导致双写分裂的概率压缩至物理极限。
   - **[新] 清理死代码**：彻底删除了未使用的旧锁全局残留变量 `_PROGRESS_LOCK_HANDLE` 和 `_PROGRESS_LOCK_DEPTH`。
3. **link-project 缺失主仓时的 Fallback（P1 修正）**：
   - 在 `link_project` 首次加载以及 `_link_child_to_parent` 进行子仓元数据更新时，如果主仓对应的子项目 `progress.json` 尚未落地，会自动 fallback 尝试加载 worktree child 处的配置文件，使 `link-project` 依然能够成功。
   - 完成后，通过双写机制自动将元数据和配置落地到主仓对应的子目录位置，完美解决了主仓 checkout 未同步子仓导致失败的逻辑缺口。
4. **主仓相对路径优先序列化（P2 修正）**：
   - 重构了 `_serialize_project_root_for_config()`。在序列化路径时，先将 `project_root` 和 `repo_root` 转换为对应的主仓路径再求相对路径，防止在 worktree 中因跨目录解析失败退化为绝对路径，避免绝对路径污染配置。
5. **修复 evaluator 数据写入**：
   - 升级了 `_store_evaluator_result()`。当处于 worktree 时，同时把 evaluator result 写进当前 worktree 和主仓库的 `progress.json` 中，确保两侧数据一致，从而避免 evaluator 状态 pending。
6. **修复父仓路由绑定发现**：
   - 修改了 `_discover_parent_route_bindings_for_child()`，如果严格的路径直接比对不通过，会回退到使用主仓库等效路径比对（`_resolve_main_repo_path`），从而使 worktree 子项目也能被顺利发现。

## 验证结果

### 自动化测试
我们在专用单元测试文件 [test_git_worktree_support.py](file:///Users/siunin/Projects/Claude-Plugins/plugins/progress-tracker/tests/test_git_worktree_support.py) 中，进一步补充了 5 个针对性测试（共包含 12 个测试用例）：
1. `test_get_main_repo_root_no_worktree` - 验证在非 worktree 下返回 `None`。
2. `test_get_main_repo_root_with_worktree` - 验证在 worktree 场景下能够正确抓出主仓库的绝对根路径。
3. `test_resolve_main_repo_path_no_worktree` - 验证非 worktree 场景下路径解析原样返回。
4. `test_resolve_main_repo_path_with_worktree` - 验证在 worktree 下成功将子项目路径转化为对应的、在主仓库中的等效路径。
5. `test_store_evaluator_result_writes_both_when_worktree` - 验证 `reconcile_evaluator` 会同时写入 worktree 副本 and 主仓库 of `progress.json`。
6. `test_discover_parent_route_bindings_with_worktree_fallback` - 验证在 fallback 逻辑下，父仓库能正确发现并绑定位于 worktree 的子仓库。
7. `test_link_project_translates_worktree_child_path` - 验证 `link-project` 保存的子仓库路径为经 worktree 转换的主仓库路径。
8. `test_get_main_repo_root_strict_avoid_false_positive` - 验证严格模式是否能避免普通路径中带有 `worktrees` 单词的误判。
9. `test_serialize_project_root_in_worktree` - 验证在 worktree 下是否能生成正确的主仓相对路径，而不是绝对路径。
10. `test_save_progress_payload_locks_correct_root` - 验证在保存阶段锁机制是否定位到了具体的 project_root。
11. `test_link_project_updates_both_wt_and_main_metadata` - 验证当注册 worktree 子仓时，其对应的 worktree 配置与 main 配置是否同时更新了父仓关联元数据。
12. `test_link_project_fallback_when_main_missing` - 真实不 mock 任何读取逻辑。验证当主仓子项目 `progress.json` 缺失时，系统成功 fallback 并在主仓落地并初始化该配置文件。

### 测试执行输出
运行 pytest：
```bash
python3 -m pytest tests/test_route_commands.py tests/test_scope_fail_closed.py tests/test_cmd_done_check_preflight.py tests/test_git_worktree_support.py -x
```
所有 67 个测试点全部通过（包含 12 个 worktree 系列测试）。
```
============================== 67 passed in 2.50s ==============================
```
