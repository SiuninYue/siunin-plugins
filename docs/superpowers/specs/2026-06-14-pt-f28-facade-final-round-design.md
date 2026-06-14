# Design: PT-F28 Progress Manager Facade Final Cleanup Round

**Date:** 2026-06-14
**Status:** Proposed
**Scope:** `plugins/progress-tracker`

## Problem & Background

This round focuses on eliminating the final four reverse-import violations from submodules to the `progress_manager` facade, achieving clean boundary separation without creating new modules. A previous draft had several blocking design flaws (e.g., signature mismatches, loss of global scope override, missing migration side effects, and incomplete allowlist cleanup).

This refined design resolves all blocking points:
1. **lifecycle_state_machine.py**: Handles signature mismatch of `save_progress_md` by resolving and passing the local `state_dir`.
2. **sprint_ledger.py**: Employs callback injection for facade functions (like `progress_transaction`, `load_progress_json`, etc.) to preserve global scope override and schema migration, while providing a pure-helper fallback for isolated test environments.
3. **wf_auto_driver.py**: Uses stateless `prog_paths` path-resolution, ensuring the tracker layout is configured and migrated locally.
4. **progress_ui_server.py**: Completely removes `progress_manager` imports. By moving `validate_plan_path` to `doc_generator.py` and `load_checkpoints` to `state_io.py`, the UI server can locally assemble callbacks required by `summary_projector`.

---

## Detailed Design

### Part 1: Refactoring sprint_ledger.py & wf_auto_driver.py

#### 1. sprint_ledger.py callback injection & fallback
We introduce a callback registry to decouple `sprint_ledger.py` from `progress_manager.py`:

```python
# In sprint_ledger.py
_progress_transaction_cb: Optional[Callable[[], Any]] = None
_load_progress_json_cb: Optional[Callable[[], Dict[str, Any]]] = None
_save_progress_json_cb: Optional[Callable[[Dict[str, Any]], None]] = None
_find_project_root_cb: Optional[Callable[[], Path]] = None

def register_callbacks(
    *,
    progress_transaction_fn: Callable[[], Any],
    load_progress_json_fn: Callable[[], Dict[str, Any]],
    save_progress_json_fn: Callable[[Dict[str, Any]], None],
    find_project_root_fn: Callable[[], Path],
) -> None:
    global _progress_transaction_cb, _load_progress_json_cb, _save_progress_json_cb, _find_project_root_cb
    _progress_transaction_cb = progress_transaction_fn
    _load_progress_json_cb = load_progress_json_fn
    _save_progress_json_cb = save_progress_json_fn
    _find_project_root_cb = find_project_root_fn
```

In `progress_manager.py`, to avoid calling callbacks before the functions are defined, we **defer the registration** to the very bottom of the file (after all functions are defined but before the `main` / parser block):
```python
# In progress_manager.py (at the bottom of the file, deferred registration)
if SPRINT_LEDGER_AVAILABLE:
    import sprint_ledger
    sprint_ledger.register_callbacks(
        progress_transaction_fn=progress_transaction,
        load_progress_json_fn=load_progress_json,
        save_progress_json_fn=save_progress_json,
        find_project_root_fn=find_project_root,
    )
```

Within `sprint_ledger.py`, all path and state operations use the callbacks if registered, falling back to pure helpers if not (e.g., in standalone unit tests):
- **Project Root**:
  ```python
  def _resolve_project_root() -> Path:
      if _find_project_root_cb is not None:
          return _find_project_root_cb()
      import prog_paths
      return prog_paths.find_project_root()
  ```
- **Ledger Path**:
  ```python
  def _default_ledger_path() -> Path:
      import prog_paths
      root = _resolve_project_root()
      # Ensure tracking layout & migration
      prog_paths.ensure_tracker_layout(root)
      prog_paths.ensure_storage_migrated(root)
      return prog_paths.get_state_dir(root) / "sprint_ledger.jsonl"
  ```
- **Transaction & I/O**:
  We align the transaction and I/O fallbacks with the real signature requirements (such as `timeout_seconds`, schema defaults, and `updated_at` touches):
  ```python
  # mark_handoff implementation:
  tx_manager = (
      _progress_transaction_cb
      if _progress_transaction_cb is not None
      else lambda: lock_manager.progress_transaction(
          timeout_seconds=10.0, project_root=_resolve_project_root()
      )
  )
  
  with tx_manager():
      if _load_progress_json_cb is not None and _save_progress_json_cb is not None:
          data = _load_progress_json_cb()
          # ... modify ...
          _save_progress_json_cb(data)
      else:
          import state_io
          import prog_paths
          root = _resolve_project_root()
          state_dir = prog_paths.get_state_dir(root)
          # Fallback read-write adhering to real state_io contracts
          data = state_io.load_progress_json(
              progress_dir=state_dir,
              apply_schema_defaults=state_io.apply_schema_defaults,
          )
          if data is None:
              raise SprintLedgerError("progress tracking not initialized")
          # ... modify ...
          state_io.save_progress_json(
              progress_dir=state_dir,
              data=data,
              touch_updated_at=True,
              apply_schema_defaults=state_io.apply_schema_defaults,
              now_fn=_utc_now_z,
          )
  ```

#### 2. wf_auto_driver.py stateless migration & paths (including read/write paths)
`wf_auto_driver.py` is always executed as a separate hook process. We eliminate all `progress_manager` imports (both read and write paths) by resolving paths via `prog_paths`:

- **Read Path (`_load_progress_direct`)**:
  ```python
  def _load_progress_direct(project_root: Optional[str]) -> dict:
      from prog_paths import find_project_root, ensure_tracker_layout, ensure_storage_migrated, get_state_dir
      import json as _json
  
      root = Path(project_root) if project_root is not None else find_project_root()
      ensure_tracker_layout(root)
      ensure_storage_migrated(root)
      state_dir = get_state_dir(root)
  
      progress_file = state_dir / "progress.json"
      if not progress_file.exists():
          return {}
      
      try:
          return _json.loads(progress_file.read_text(encoding="utf-8"))
      except Exception:
          return {}
  ```

- **Write Path (`_write_back_pending_action`)**:
  ```python
  def _write_back_pending_action(pending_action: str, project_root: Optional[str]) -> None:
      """在文件锁内原子写回 pending_action。"""
      from prog_paths import find_project_root
      from lifecycle_state_machine import acquire_lock
      from pathlib import Path
      import json
      import os
  
      # 找到 progress.json 路径，使用 prog_paths.find_project_root() 代替 progress_manager.find_project_root()
      project_path = Path(project_root) if project_root else find_project_root()
      state_dir = project_path / "docs" / "progress-tracker" / "state"
      progress_file = state_dir / "progress.json"
      lock_path = state_dir / "progress.lock"
  
      if not progress_file.exists():
          return
  
      with acquire_lock(lock_path):
          data = json.loads(progress_file.read_text(encoding="utf-8"))
          workflow_state = data.get("workflow_state")
          if not workflow_state:
              return
          workflow_state["pending_action"] = pending_action
          # 原子写入
          tmp = progress_file.with_suffix(".tmp")
          tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
          os.replace(tmp, progress_file)
  ```

---

### Part 2: Refactoring lifecycle_state_machine.py

`lifecycle_state_machine.py` needs to call `save_progress_md`. Instead of importing it from `progress_manager`, we import `doc_generator.generate_progress_md` and `state_io.save_progress_md` and pass the resolved `state_dir`:

```python
        # 4. 更新 progress.md（非阻塞）
        try:
            from doc_generator import generate_progress_md
            from state_io import save_progress_md
            md_content = generate_progress_md(data)
            save_progress_md(state_dir, md_content)
        except Exception:
            pass  # markdown 更新失败不影响核心功能
```

---

### Part 3: Refactoring progress_ui_server.py

We completely eliminate the `progress_manager` dependency in `progress_ui_server.py` to enable its removal from the `.pm_boundary_allowlist`.

#### 1. Relocate `validate_plan_path`
- **Move logic**: Relocate the actual logic of `validate_plan_path` from `progress_manager.py` into `doc_generator.py`. **IMPORTANT**: The recursive upward directory search for plan files (up to the git repository root resolved via `prog_paths.resolve_repo_root()`) must be explicitly preserved to support plan files generated by the `writing-plans` skill (which may reside at the repo/worktree root level rather than the current workspace subfolder).
  
  Specifically, `doc_generator.validate_plan_path` will implement the following logic:
  ```python
  if require_exists:
      base_root = (target_root or prog_paths.find_project_root()).resolve()
      absolute_path = base_root / normalized
      if not absolute_path.exists():
          found = False
          try:
              git_root = prog_paths.resolve_repo_root(base_root).resolve()
          except Exception:
              git_root = None
          cursor = base_root
          while True:
              cursor = cursor.parent
              if (cursor / normalized).exists():
                  found = True
                  break
              if (git_root is not None and cursor == git_root) or cursor == cursor.parent:
                  break
          if not found:
              return {
                  "valid": False,
                  "normalized_path": None,
                  "error": f"plan_path does not exist: {normalized}",
              }
  ```

- **Expose wrappers**:
  - `progress_manager.py` becomes a thin wrapper:
    ```python
    def validate_plan_path(plan_path: Optional[str], require_exists: bool = False, target_root: Optional[Path] = None):
        import doc_generator
        return doc_generator.validate_plan_path(plan_path, require_exists, target_root)
    validate_plan_path.is_wrapper = True
    ```
- **Update `validate_plan_document`**:
  Make the `validate_plan_path_fn` parameter optional in `doc_generator.py`'s signature:
  ```python
  def validate_plan_document(
      plan_path: str,
      target_root: Optional[Path] = None,
      *,
      find_project_root_fn: Optional[Callable[[], Path]] = None,
      validate_plan_path_fn: Optional[Callable[..., Dict[str, Any]]] = None,
  ) -> Dict[str, Any]:
      val_fn = validate_plan_path_fn or validate_plan_path
      path_validation = val_fn(plan_path, require_exists=True, target_root=target_root)
      ...
  ```

#### 2. Down-sink `load_checkpoints` to `state_io.py`
- **Move logic**: Define `load_checkpoints_from_file(path: Path) -> Dict[str, Any]` and `load_checkpoints(progress_dir: Path) -> Dict[str, Any]` in `state_io.py`.
- **Expose wrapper**: In `progress_manager.py`:
  ```python
  def load_checkpoints(path: Optional[Path] = None) -> Dict[str, Any]:
      import state_io
      checkpoints_path = path or (get_progress_dir() / CHECKPOINTS_JSON)
      return state_io.load_checkpoints_from_file(checkpoints_path)
  load_checkpoints.is_wrapper = True
  ```

#### 3. Update `progress_ui_server.py` imports and status projection
- **Remove imports**: Completely remove the module-level import of `progress_manager` and the `PROGRESS_MANAGER_AVAILABLE` checks.
- **Direct imports**:
  ```python
  from doc_generator import validate_plan_path, validate_plan_document
  from state_io import compare_contexts
  ```
- **Local callback assembly for status summary**:
  In `handle_get_status_summary`:
  ```python
  import summary_projector
  import state_io
  
  def ui_apply_schema_defaults(data: dict) -> None:
      state_io.apply_schema_defaults(data)

  def ui_load_checkpoints(path: Optional[Path] = None) -> Dict[str, Any]:
      resolved_path = path or prog_paths.get_checkpoints_path(self.working_dir)
      return state_io.load_checkpoints_from_file(resolved_path)

  try:
      return summary_projector.load_status_summary_projection(
          str(self.working_dir),
          apply_schema_defaults_fn=ui_apply_schema_defaults,
          load_checkpoints_fn=ui_load_checkpoints,
          validate_plan_path_fn=lambda p, require_exists=False, target_root=None: validate_plan_path(p, require_exists=require_exists, target_root=target_root or self.working_dir),
          validate_plan_document_fn=lambda p, target_root=None: validate_plan_document(p, target_root=target_root or self.working_dir),
      )
  except Exception as exc:
      # Fallback...
  ```
- **Remove global scope override setting**:
  We no longer set `progress_manager_module._PROJECT_ROOT_OVERRIDE` in `create_handler` and `main` because `progress_ui_server` does not call `progress_manager` functions.

---

## Verification Plan

### Automated Tests
- Run the full test suite to verify no regressions:
  `uv run pytest tests/ -q`
- Run PM boundary checks:
  `./scripts/check_pm_boundary.sh`
- Run doc generators check:
  `python3 plugins/progress-tracker/hooks/scripts/generate_prog_docs.py --check`
