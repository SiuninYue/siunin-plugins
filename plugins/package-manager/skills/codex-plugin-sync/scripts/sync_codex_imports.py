#!/usr/bin/env python3
"""Sync Claude plugin resources into Codex wrappers or Codex plugin SOP outputs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_WORKSPACE_PLUGINS = "/Users/siunin/Projects/Claude-Plugins/plugins"

SUPPORTED_INCLUDE_DIRS = ("skills", "commands", "agents")
OPTIONAL_PLUGIN_DIRS = ("templates", "assets")
INCLUDE_DIR_CANDIDATES: dict[str, tuple[Path, ...]] = {
    "skills": (
        Path("skills"),
        Path(".claude-plugin/skills"),
        Path(".claude/skills"),
    ),
    "commands": (
        Path("commands"),
        Path(".claude-plugin/commands"),
        Path(".claude/commands"),
    ),
    "agents": (
        Path("agents"),
        Path(".claude-plugin/agents"),
        Path(".claude/agents"),
    ),
}
PLACEHOLDER_BRACED = "${CLAUDE_PLUGIN_ROOT}"
PLACEHOLDER_PLAIN_PATTERN = re.compile(r"(?<![A-Za-z0-9_])\$CLAUDE_PLUGIN_ROOT\b")
HOOK_EVENT_PATTERN_USER_PROMPT_SUBMIT = re.compile(r"(?<![A-Za-z0-9_])UserPromptSubmit(?![A-Za-z0-9_])")
TOP_LEVEL_KEY_PATTERN = re.compile(r"^([A-Za-z0-9_-]+):(.*)$")
SEMVER_PATTERN = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?"
    r"(?:\+[0-9A-Za-z.-]+)?$"
)


@dataclass
class PluginRecord:
    wrapper_name: str
    source: Path
    include_dirs: list[str]
    plugin_name: str


@dataclass
class PluginStats:
    files_processed: int = 0
    files_converted: int = 0
    fields_removed: int = 0
    fields_added: int = 0
    placeholder_rewrites: int = 0
    placeholder_hits: int = 0
    hook_events_mapped: int = 0
    prompts_synced: int = 0


@dataclass
class PluginResult:
    wrapper_name: str
    plugin_name: str
    source_selected: str | None = None
    source_origin: str | None = None
    target_path: str | None = None
    include_dirs_requested: list[str] = field(default_factory=list)
    include_dirs_applied: list[str] = field(default_factory=list)
    extras_included: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: PluginStats = field(default_factory=PluginStats)
    status: str = "ok"
    error: str | None = None


def default_manifest_path() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    return codex_home / "skills" / "claude-migration-manifest.json"


def default_codex_skills_root() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    return codex_home / "skills"


def default_codex_plugins_root() -> Path:
    return Path(DEFAULT_WORKSPACE_PLUGINS).parent / "plugins-codex"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sync Claude plugin resources into Codex skill wrappers or convert them "
            "into Codex plugin SOP directories."
        )
    )
    parser.add_argument(
        "--plugins",
        default="all",
        help="Target plugins: 'all' or comma-separated wrapper/plugin names.",
    )
    parser.add_argument(
        "--manifest",
        default=str(default_manifest_path()),
        help="Absolute path to claude-migration-manifest.json.",
    )
    parser.add_argument(
        "--workspace-plugins",
        default=DEFAULT_WORKSPACE_PLUGINS,
        help="Workspace plugins directory for workspace-first resolution.",
    )
    parser.add_argument(
        "--record-source",
        choices=("auto", "manifest", "workspace"),
        default="auto",
        help=(
            "Plugin record source. auto -> wrapper mode uses manifest, codex-plugin "
            "mode uses workspace scan."
        ),
    )
    parser.add_argument(
        "--codex-skills-root",
        default=str(default_codex_skills_root()),
        help="Codex skills root directory (default: $CODEX_HOME/skills).",
    )
    parser.add_argument(
        "--codex-plugins-root",
        default=str(default_codex_plugins_root()),
        help=(
            "Output root for converted Codex plugins when "
            "--output-mode=codex-plugin."
        ),
    )
    parser.add_argument(
        "--output-mode",
        choices=("wrapper-skill", "codex-plugin"),
        default="wrapper-skill",
        help=(
            "wrapper-skill -> update ~/.codex/skills wrappers; codex-plugin -> "
            "export full Codex plugin directories with .codex-plugin/plugin.json."
        ),
    )
    parser.add_argument(
        "--source-policy",
        choices=("workspace-first", "manifest-only", "workspace-only"),
        default="workspace-first",
        help="Source resolution policy for plugin directories.",
    )
    parser.add_argument(
        "--missing-source-policy",
        choices=("error", "skip"),
        default="skip",
        help=(
            "Behavior when a plugin source cannot be resolved: "
            "error -> fail run, skip -> continue with warning."
        ),
    )
    parser.add_argument(
        "--extra-dirs",
        choices=("auto", "always", "never"),
        default="auto",
        help="How to include plugin-level hooks/scripts directories.",
    )
    parser.add_argument(
        "--placeholder-mode",
        choices=("rewrite", "warn", "fail"),
        default="rewrite",
        help="How to handle ${CLAUDE_PLUGIN_ROOT} placeholders.",
    )
    parser.add_argument(
        "--hook-event-map",
        choices=("none", "userpromptsubmit-beforeagent"),
        default="none",
        help=(
            "Optional hook event compatibility mapping for hooks.json files. "
            "userpromptsubmit-beforeagent maps UserPromptSubmit -> BeforeAgent."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and report changes without writing output files.",
    )
    parser.add_argument(
        "--report",
        help="Optional path to save JSON report.",
    )
    parser.add_argument(
        "--sync-prompts",
        choices=("none", "project", "global", "both"),
        default="none",
        help=(
            "Sync plugin commands into Codex prompt files. "
            "project -> <project-root>/.codex/prompts, global -> $CODEX_HOME/prompts."
        ),
    )
    parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="Project root used by --sync-prompts=project|both.",
    )
    parser.add_argument(
        "--global-prompts-root",
        default=str(Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "prompts"),
        help="Global prompts directory used by --sync-prompts=global|both.",
    )
    parser.add_argument(
        "--prompt-args-token",
        default="$ARGUMENTS",
        help=(
            "Token text used in generated prompts for commands with args=\"{user_input}\" "
            "(default: $ARGUMENTS)."
        ),
    )
    return parser.parse_args(argv)


def title_case_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.replace("_", "-").split("-") if part)


def normalize_include_dirs(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    dirs: list[str] = []
    for item in value:
        if isinstance(item, str) and item in SUPPORTED_INCLUDE_DIRS:
            dirs.append(item)
    return dirs


def resolve_include_source_dir(source_root: Path, include_dir: str) -> Path | None:
    candidates = INCLUDE_DIR_CANDIDATES.get(include_dir, (Path(include_dir),))
    for relative in candidates:
        candidate = source_root / relative
        if candidate.is_dir():
            return candidate
    return None


def format_missing_include_warning(source_root: Path, include_dir: str) -> str:
    candidates = INCLUDE_DIR_CANDIDATES.get(include_dir, (Path(include_dir),))
    rendered = ", ".join(str(source_root / rel) for rel in candidates)
    return f"Missing source directory for '{include_dir}' (tried: {rendered})"


def parse_semver(version: str) -> tuple[int, int, int, int, str] | None:
    match = SEMVER_PATTERN.fullmatch(version)
    if not match:
        return None
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    pre = match.group("pre") or ""
    is_stable = 1 if not pre else 0
    return major, minor, patch, is_stable, pre


def infer_plugin_name(source: Path) -> str:
    parts = source.parts

    for index in range(len(parts) - 1):
        if parts[index] != "plugins":
            continue
        candidate = parts[index + 1]
        if candidate and candidate not in {"cache", "marketplaces"}:
            return candidate

    if "cache" in parts:
        cache_index = parts.index("cache")
        plugin_index = cache_index + 2
        if plugin_index < len(parts):
            candidate = parts[plugin_index]
            if candidate:
                return candidate

    return source.name


def resolve_latest_version_source(source: Path) -> Path | None:
    if source.is_dir():
        return source

    if parse_semver(source.name) is None:
        return None

    parent = source.parent
    if not parent.is_dir():
        return None

    versioned_dirs: list[tuple[tuple[int, int, int, int, str], Path]] = []
    for child in parent.iterdir():
        if not child.is_dir():
            continue
        parsed = parse_semver(child.name)
        if parsed is None:
            continue
        versioned_dirs.append((parsed, child))

    if not versioned_dirs:
        return None

    versioned_dirs.sort(key=lambda item: item[0], reverse=True)
    return versioned_dirs[0][1]


def load_manifest(path: Path) -> list[PluginRecord]:
    if not path.is_file():
        raise FileNotFoundError(f"Manifest not found: {path}")
    with path.open("r", encoding="utf-8") as file_handle:
        raw = json.load(file_handle)
    if not isinstance(raw, list):
        raise ValueError("Manifest must contain a JSON array")

    records: list[PluginRecord] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        wrapper_name = entry.get("skill_name")
        source = entry.get("source")
        if not isinstance(wrapper_name, str) or not isinstance(source, str):
            continue
        include_dirs = normalize_include_dirs(entry.get("include_dirs"))
        source_path = Path(source).expanduser()
        plugin_name = infer_plugin_name(source_path)
        records.append(
            PluginRecord(
                wrapper_name=wrapper_name,
                source=source_path,
                include_dirs=include_dirs,
                plugin_name=plugin_name,
            )
        )
    return records


def detect_include_dirs(source_root: Path) -> list[str]:
    include_dirs: list[str] = []
    for include_dir in SUPPORTED_INCLUDE_DIRS:
        if resolve_include_source_dir(source_root, include_dir) is not None:
            include_dirs.append(include_dir)
    return include_dirs


def load_workspace_records(workspace_plugins: Path) -> list[PluginRecord]:
    if not workspace_plugins.is_dir():
        raise FileNotFoundError(f"Workspace plugins directory not found: {workspace_plugins}")

    records: list[PluginRecord] = []
    for child in sorted(workspace_plugins.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        plugin_name = infer_plugin_name(child)
        records.append(
            PluginRecord(
                wrapper_name=plugin_name,
                source=child,
                include_dirs=detect_include_dirs(child),
                plugin_name=plugin_name,
            )
        )
    return records


def select_records(records: list[PluginRecord], selection: str) -> list[PluginRecord]:
    if selection.strip().lower() == "all":
        return records

    tokens = {token.strip() for token in selection.split(",") if token.strip()}
    if not tokens:
        raise ValueError("--plugins is empty")

    selected: list[PluginRecord] = []
    unresolved = set(tokens)
    for record in records:
        if record.wrapper_name in tokens or record.plugin_name in tokens:
            selected.append(record)
            unresolved.discard(record.wrapper_name)
            unresolved.discard(record.plugin_name)

    if unresolved:
        raise ValueError(
            "Unknown plugin selector(s): " + ", ".join(sorted(unresolved))
        )
    return selected


def resolve_source(
    record: PluginRecord,
    workspace_plugins: Path,
    source_policy: str,
) -> tuple[Path, str]:
    workspace_candidate = workspace_plugins / record.plugin_name
    manifest_source = record.source
    latest_manifest_source = resolve_latest_version_source(manifest_source)

    if source_policy == "workspace-first":
        if workspace_candidate.is_dir():
            return workspace_candidate, "workspace"
        if manifest_source.is_dir():
            return manifest_source, "manifest"
        if latest_manifest_source and latest_manifest_source.is_dir():
            return latest_manifest_source, "manifest-latest-version"
    elif source_policy == "workspace-only":
        if workspace_candidate.is_dir():
            return workspace_candidate, "workspace"
    elif source_policy == "manifest-only":
        if manifest_source.is_dir():
            return manifest_source, "manifest"
        if latest_manifest_source and latest_manifest_source.is_dir():
            return latest_manifest_source, "manifest-latest-version"

    raise FileNotFoundError(
        f"Cannot resolve source for {record.wrapper_name} using policy {source_policy}"
    )


def split_frontmatter(text: str) -> tuple[str, str] | None:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            frontmatter = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            return frontmatter, body
    return None


def count_top_level_keys(frontmatter: str) -> int:
    count = 0
    for line in frontmatter.splitlines():
        if line.startswith((" ", "\t")):
            continue
        if TOP_LEVEL_KEY_PATTERN.match(line):
            count += 1
    return count


def extract_scalar_value(frontmatter: str, key: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.*)$", re.MULTILINE)
    match = pattern.search(frontmatter)
    if not match:
        return None
    value = match.group(1).strip()
    if not value:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_top_level_blocks(frontmatter: str) -> list[tuple[str | None, list[str]]]:
    lines = frontmatter.splitlines(keepends=True)
    blocks: list[tuple[str | None, list[str]]] = []
    prelude: list[str] = []
    current_key: str | None = None
    current_lines: list[str] = []

    for line in lines:
        is_top_level = bool(TOP_LEVEL_KEY_PATTERN.match(line)) and not line.startswith((" ", "\t"))
        if is_top_level:
            if current_key is None:
                if prelude:
                    blocks.append((None, prelude))
                    prelude = []
            else:
                blocks.append((current_key, current_lines))
            current_key = TOP_LEVEL_KEY_PATTERN.match(line).group(1)
            current_lines = [line]
            continue

        if current_key is None:
            prelude.append(line)
        else:
            current_lines.append(line)

    if current_key is not None:
        blocks.append((current_key, current_lines))
    elif prelude:
        blocks.append((None, prelude))

    return blocks


def normalize_frontmatter(
    text: str,
    kind: str,
    default_name: str,
) -> tuple[str, int, int, int]:
    parsed = split_frontmatter(text)

    if parsed is None:
        if kind == "skill":
            description = f'Imported skill "{default_name}" from Claude plugin resources.'
            frontmatter = (
                "---\n"
                f"name: {json.dumps(default_name, ensure_ascii=False)}\n"
                f"description: {json.dumps(description, ensure_ascii=False)}\n"
                "---\n"
            )
            return frontmatter + text, 0, 2, 1
        if kind in {"command", "agent"}:
            frontmatter = "---\n" f"name: {json.dumps(default_name, ensure_ascii=False)}\n" "---\n"
            return frontmatter + text, 0, 1, 1
        return text, 0, 0, 0

    frontmatter, body = parsed

    if kind == "skill":
        name_value = extract_scalar_value(frontmatter, "name") or default_name
        description_value = extract_scalar_value(frontmatter, "description")
        if not description_value:
            description_value = f'Imported skill "{default_name}" from Claude plugin resources.'

        removed_keys = max(
            count_top_level_keys(frontmatter)
            - int(extract_scalar_value(frontmatter, "name") is not None)
            - int(extract_scalar_value(frontmatter, "description") is not None),
            0,
        )
        added_fields = int(extract_scalar_value(frontmatter, "name") is None) + int(
            extract_scalar_value(frontmatter, "description") is None
        )
        normalized = (
            "---\n"
            f"name: {json.dumps(name_value, ensure_ascii=False)}\n"
            f"description: {json.dumps(description_value, ensure_ascii=False)}\n"
            "---\n"
            + body
        )
        return normalized, removed_keys, added_fields, 1

    if kind in {"command", "agent"}:
        blocks = parse_top_level_blocks(frontmatter)
        output_blocks: list[tuple[str | None, list[str]]] = []
        removed_fields = 0
        has_name = False

        for key, lines in blocks:
            if key is None:
                output_blocks.append((key, lines))
                continue
            key_lower = key.lower()
            if key_lower in {"model", "madel"}:
                removed_fields += 1
                continue
            if key_lower == "name":
                has_name = True
            output_blocks.append((key, lines))

        added_fields = 0
        if not has_name:
            name_line = f"name: {json.dumps(default_name, ensure_ascii=False)}\n"
            if output_blocks and output_blocks[0][0] is None:
                output_blocks = [
                    output_blocks[0],
                    ("name", [name_line]),
                    *output_blocks[1:],
                ]
            else:
                output_blocks = [("name", [name_line]), *output_blocks]
            added_fields = 1

        normalized_frontmatter = "".join("".join(lines) for _, lines in output_blocks)
        normalized = "---\n" + normalized_frontmatter + "---\n" + body
        return normalized, removed_fields, added_fields, 1

    return text, 0, 0, 0


def detect_doc_kind(wrapper_relative_path: Path) -> tuple[str | None, str | None]:
    parts = wrapper_relative_path.parts
    if len(parts) >= 4 and parts[0] == "references" and parts[1] == "skills" and parts[-1] == "SKILL.md":
        return "skill", parts[2]
    if len(parts) >= 3 and parts[0] == "references" and parts[1] == "commands" and wrapper_relative_path.suffix == ".md":
        return "command", wrapper_relative_path.stem
    if len(parts) >= 3 and parts[0] == "references" and parts[1] == "agents" and wrapper_relative_path.suffix == ".md":
        return "agent", wrapper_relative_path.stem
    if len(parts) >= 2 and parts[0] == "skills" and parts[-1] == "SKILL.md":
        return "skill", parts[1]
    if len(parts) >= 2 and parts[0] == "commands" and wrapper_relative_path.suffix == ".md":
        return "command", wrapper_relative_path.stem
    if len(parts) >= 2 and parts[0] == "agents" and wrapper_relative_path.suffix == ".md":
        return "agent", wrapper_relative_path.stem
    return None, None


def has_plugin_root_placeholder(text: str) -> bool:
    return PLACEHOLDER_BRACED in text or bool(PLACEHOLDER_PLAIN_PATTERN.search(text))


def rewrite_placeholders(text: str, replacement: str) -> tuple[str, int]:
    hits = text.count(PLACEHOLDER_BRACED)
    rewritten = text.replace(PLACEHOLDER_BRACED, replacement)

    plain_hits = len(PLACEHOLDER_PLAIN_PATTERN.findall(rewritten))
    rewritten = PLACEHOLDER_PLAIN_PATTERN.sub(replacement, rewritten)
    return rewritten, hits + plain_hits


def is_hooks_manifest(relative_path: Path) -> bool:
    if relative_path.name != "hooks.json":
        return False
    parts = relative_path.parts
    if len(parts) == 1 and parts[0] == "hooks.json":
        return True
    return len(parts) >= 2 and parts[-2] == "hooks"


def rewrite_hook_events(text: str, mode: str) -> tuple[str, int]:
    if mode != "userpromptsubmit-beforeagent":
        return text, 0
    hits = len(HOOK_EVENT_PATTERN_USER_PROMPT_SUBMIT.findall(text))
    if hits == 0:
        return text, 0
    return HOOK_EVENT_PATTERN_USER_PROMPT_SUBMIT.sub("BeforeAgent", text), hits


def process_text_file(
    file_path: Path,
    wrapper_root: Path,
    placeholder_mode: str,
    hook_event_map_mode: str,
    placeholder_replacement: str,
    result: PluginResult,
    apply_frontmatter: bool,
) -> bool:
    try:
        original_text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False

    changed = False
    text = original_text
    relative = file_path.relative_to(wrapper_root)

    if apply_frontmatter:
        kind, default_name = detect_doc_kind(relative)
        if kind and default_name:
            normalized, removed, added, converted = normalize_frontmatter(text, kind, default_name)
            text = normalized
            result.stats.fields_removed += removed
            result.stats.fields_added += added
            result.stats.files_converted += converted
            changed = changed or (text != original_text)

    placeholder_detected = has_plugin_root_placeholder(text)
    if placeholder_detected:
        result.stats.placeholder_hits += 1
        if placeholder_mode == "fail":
            raise RuntimeError(
                f"Placeholder {PLACEHOLDER_BRACED} detected in {relative}"
            )
        if placeholder_mode == "warn":
            warning = (
                f"Placeholder detected in {relative}; kept unchanged due to "
                "--placeholder-mode=warn"
            )
            if warning not in result.warnings:
                result.warnings.append(warning)
        elif placeholder_mode == "rewrite":
            rewritten, rewrites = rewrite_placeholders(text, placeholder_replacement)
            text = rewritten
            result.stats.placeholder_rewrites += rewrites
            changed = changed or rewrites > 0

    if hook_event_map_mode != "none" and is_hooks_manifest(relative):
        rewritten, mapped = rewrite_hook_events(text, hook_event_map_mode)
        if mapped > 0:
            text = rewritten
            result.stats.hook_events_mapped += mapped
            changed = True

    if changed:
        file_path.write_text(text, encoding="utf-8")

    result.stats.files_processed += 1
    return placeholder_detected


def copy_directory(src: Path, dest: Path) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dest, dirs_exist_ok=True)


def extract_skill_and_args(command_body: str) -> tuple[str | None, str | None]:
    skill_match = re.search(
        r'^\s*-\s*skill:\s*"[^":]+:([^"\n]+)"\s*$',
        command_body,
        flags=re.MULTILINE,
    )
    args_match = re.search(
        r'^\s*-\s*args:\s*"([^"]*)"\s*$',
        command_body,
        flags=re.MULTILINE,
    )
    skill = skill_match.group(1).strip() if skill_match else None
    args_value = args_match.group(1).strip() if args_match else None
    return skill, args_value


def build_prompt_from_command(command_text: str, command_name: str, prompt_args_token: str) -> str:
    parsed = split_frontmatter(command_text)
    if parsed is None:
        description = f"Run {command_name} workflow"
        body = command_text.strip()
    else:
        frontmatter, body = parsed
        description = extract_scalar_value(frontmatter, "description") or f"Run {command_name} workflow"

    skill_name, args_value = extract_skill_and_args(body)
    if skill_name:
        prompt_lines = [f"Use the `${skill_name}` skill now."]
        if args_value == "{user_input}":
            prompt_lines.append(
                f"If arguments are provided, treat them as extra context: `{prompt_args_token}`."
            )
        elif args_value:
            prompt_lines.append(f"Pass this exact argument: `{args_value}`.")
        body_text = "\n".join(prompt_lines)
    else:
        body_text = body.strip()

    return (
        "---\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
        f"{body_text}\n"
    )


def sync_prompts_from_commands(
    source_commands_dir: Path,
    prompts_root: Path,
    dry_run: bool,
    result: PluginResult,
    prompt_args_token: str,
) -> int:
    if not source_commands_dir.is_dir():
        result.warnings.append(f"Missing commands directory for prompt sync: {source_commands_dir}")
        return 0

    command_files = sorted(source_commands_dir.glob("*.md"))
    synced = 0
    if not dry_run:
        prompts_root.mkdir(parents=True, exist_ok=True)

    for command_file in command_files:
        prompt_name = command_file.name
        command_text = command_file.read_text(encoding="utf-8")
        prompt_text = build_prompt_from_command(
            command_text,
            command_file.stem,
            prompt_args_token,
        )
        target_file = prompts_root / prompt_name
        if not dry_run:
            target_file.write_text(prompt_text, encoding="utf-8")
        synced += 1

    result.stats.prompts_synced += synced
    return synced


def load_json_object(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def read_source_plugin_manifest(source_root: Path) -> dict:
    claude_manifest = load_json_object(source_root / ".claude-plugin" / "plugin.json")
    if claude_manifest is not None:
        return claude_manifest
    codex_manifest = load_json_object(source_root / ".codex-plugin" / "plugin.json")
    if codex_manifest is not None:
        return codex_manifest
    return {}


def sanitize_string_list(value: object, limit: int | None = None) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if not candidate:
            continue
        result.append(candidate)
        if limit is not None and len(result) >= limit:
            break
    return result


def infer_interface_capabilities(
    include_dirs: list[str],
    extras_included: list[str],
) -> list[str]:
    capabilities: list[str] = []
    if "skills" in include_dirs:
        capabilities.append("Instructional")
    if "commands" in include_dirs:
        capabilities.append("Interactive")
    if "agents" in include_dirs:
        capabilities.append("Agentic")
    if "hooks" in extras_included or "scripts" in extras_included:
        capabilities.append("Automation")
    return capabilities or ["Productivity"]


def resolve_hooks_manifest_relative(staged_plugin: Path) -> str | None:
    hooks_manifest = staged_plugin / "hooks" / "hooks.json"
    if hooks_manifest.is_file():
        return "./hooks/hooks.json"
    legacy_hooks_manifest = staged_plugin / "hooks.json"
    if legacy_hooks_manifest.is_file():
        return "./hooks.json"
    return None


def build_codex_plugin_manifest(
    *,
    plugin_name: str,
    source_manifest: dict,
    staged_plugin: Path,
    include_dirs: list[str],
    extras_included: list[str],
) -> dict:
    description = source_manifest.get("description")
    if not isinstance(description, str) or not description.strip():
        description = f"Converted from Claude plugin {plugin_name}"
    description = description.strip()

    version = source_manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        version = "0.1.0"
    version = version.strip()

    author_value = source_manifest.get("author")
    if isinstance(author_value, dict):
        author: dict[str, str] = {}
        for key in ("name", "email", "url"):
            val = author_value.get(key)
            if isinstance(val, str) and val.strip():
                author[key] = val.strip()
        if "name" not in author:
            author["name"] = "unknown"
    elif isinstance(author_value, str) and author_value.strip():
        author = {"name": author_value.strip()}
    else:
        author = {"name": "unknown"}

    manifest: dict[str, object] = {
        "name": plugin_name,
        "version": version,
        "description": description,
        "author": author,
        "license": source_manifest.get("license", "MIT"),
        "keywords": sanitize_string_list(source_manifest.get("keywords")),
    }

    homepage = source_manifest.get("homepage")
    if isinstance(homepage, str) and homepage.strip():
        manifest["homepage"] = homepage.strip()

    repository = source_manifest.get("repository")
    if isinstance(repository, str) and repository.strip():
        manifest["repository"] = repository.strip()

    if (staged_plugin / "skills").is_dir():
        manifest["skills"] = "./skills/"

    hooks_relative = resolve_hooks_manifest_relative(staged_plugin)
    if hooks_relative:
        manifest["hooks"] = hooks_relative

    mcp_relative = None
    if (staged_plugin / ".mcp.json").is_file():
        mcp_relative = "./.mcp.json"
    elif (staged_plugin / "mcp.json").is_file():
        mcp_relative = "./mcp.json"
    if mcp_relative:
        manifest["mcpServers"] = mcp_relative

    apps_relative = None
    if (staged_plugin / ".app.json").is_file():
        apps_relative = "./.app.json"
    elif (staged_plugin / "app.json").is_file():
        apps_relative = "./app.json"
    if apps_relative:
        manifest["apps"] = apps_relative

    display_name = title_case_slug(plugin_name)
    developer_name = author.get("name", "unknown")
    interface = {
        "displayName": display_name,
        "shortDescription": description[:120],
        "longDescription": f"Converted from Claude plugin '{plugin_name}' with codex-plugin-sync.",
        "developerName": developer_name,
        "category": "Productivity",
        "capabilities": infer_interface_capabilities(include_dirs, extras_included),
        "defaultPrompt": [
            f"Use {display_name} workflows in this repository.",
            f"Run {display_name} commands for this task.",
            f"Apply {display_name} guidance before implementation.",
        ],
    }
    manifest["interface"] = interface
    return manifest


def generate_wrapper_skill(
    wrapper_name: str,
    plugin_name: str,
    source_path: Path,
    included_dirs: list[str],
) -> str:
    included_text = ", ".join(included_dirs) if included_dirs else "(none)"
    return (
        "---\n"
        f"name: {json.dumps(wrapper_name)}\n"
        f"description: {json.dumps(f'Imported from Claude plugin path {source_path}. Use when Codex should reuse this plugin\'s skills, agents, or commands for similar tasks and workflows.')}\n"
        "---\n\n"
        f"# {title_case_slug(plugin_name)}\n\n"
        "Import and adapt workflows from the original Claude plugin resources.\n\n"
        "## Workflow\n\n"
        "1. Review `references/skills/` first when domain guidance is needed.\n"
        "2. Review `references/agents/` when role-specific collaboration patterns are needed.\n"
        "3. Review `references/commands/` when a command-style procedure is needed.\n"
        "4. Adapt imported instructions to the current repository context before execution.\n\n"
        "## Source\n\n"
        f"- Path: `{source_path}`\n"
        f"- Included directories: {included_text}\n"
        f"- Original plugin name: `{plugin_name}`\n"
    )


def generate_openai_yaml(wrapper_name: str, plugin_name: str) -> str:
    display_name = title_case_slug(plugin_name)
    return (
        "interface:\n"
        f'  display_name: "{display_name}"\n'
        f'  short_description: "Imported Claude workflows for {display_name}"\n'
        f'  default_prompt: "Use ${wrapper_name} to import and adapt workflows from migrated Claude plugin resources."\n'
    )


def deploy_directory(
    staged_path: Path,
    destination_path: Path,
    backup_root: Path,
) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / destination_path.name

    moved_existing = False
    if destination_path.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        if backup_path.exists():
            shutil.rmtree(backup_path)
        shutil.move(str(destination_path), str(backup_path))
        moved_existing = True

    try:
        shutil.move(str(staged_path), str(destination_path))
    except Exception as error:
        if moved_existing and backup_path.exists() and not destination_path.exists():
            shutil.move(str(backup_path), str(destination_path))
        raise RuntimeError(f"Failed to deploy path {destination_path.name}: {error}") from error


def sync_plugin(
    record: PluginRecord,
    source_root: Path,
    codex_skills_root: Path,
    extra_dirs_mode: str,
    placeholder_mode: str,
    hook_event_map_mode: str,
    dry_run: bool,
    backup_root: Path,
    sync_prompts_mode: str,
    prompt_args_token: str,
    project_prompts_root: Path,
    global_prompts_root: Path,
) -> PluginResult:
    result = PluginResult(
        wrapper_name=record.wrapper_name,
        plugin_name=record.plugin_name,
        source_selected=str(source_root),
        include_dirs_requested=list(record.include_dirs),
    )

    tmp_root = Path(tempfile.mkdtemp(prefix="codex-sync-"))
    staged_wrapper = tmp_root / record.wrapper_name

    include_mapping = {
        "skills": Path("references/skills"),
        "commands": Path("references/commands"),
        "agents": Path("references/agents"),
    }

    try:
        staged_wrapper.mkdir(parents=True, exist_ok=True)

        for include_dir in record.include_dirs:
            if include_dir not in include_mapping:
                result.warnings.append(f"Unsupported include dir in manifest: {include_dir}")
                continue
            source_dir = resolve_include_source_dir(source_root, include_dir)
            if source_dir is None:
                result.warnings.append(format_missing_include_warning(source_root, include_dir))
                continue

            target_dir = staged_wrapper / include_mapping[include_dir]
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            copy_directory(source_dir, target_dir)
            result.include_dirs_applied.append(include_dir)

        placeholder_detected = False
        for file_path in staged_wrapper.rglob("*"):
            if not file_path.is_file():
                continue
            if process_text_file(
                file_path=file_path,
                wrapper_root=staged_wrapper,
                placeholder_mode=placeholder_mode,
                hook_event_map_mode=hook_event_map_mode,
                placeholder_replacement=f"${{CODEX_HOME:-$HOME/.codex}}/skills/{record.wrapper_name}",
                result=result,
                apply_frontmatter=True,
            ):
                placeholder_detected = True

        include_extras = extra_dirs_mode == "always" or (
            extra_dirs_mode == "auto" and placeholder_detected
        )
        if include_extras:
            for extra_dir in ("hooks", "scripts"):
                source_extra = source_root / extra_dir
                if not source_extra.is_dir():
                    continue
                target_extra = staged_wrapper / extra_dir
                copy_directory(source_extra, target_extra)
                result.extras_included.append(extra_dir)

            for extra in result.extras_included:
                extra_root = staged_wrapper / extra
                for file_path in extra_root.rglob("*"):
                    if not file_path.is_file():
                        continue
                    process_text_file(
                        file_path=file_path,
                        wrapper_root=staged_wrapper,
                        placeholder_mode=placeholder_mode,
                        hook_event_map_mode=hook_event_map_mode,
                        placeholder_replacement=f"${{CODEX_HOME:-$HOME/.codex}}/skills/{record.wrapper_name}",
                        result=result,
                        apply_frontmatter=False,
                    )

        included_dirs_for_wrapper = list(result.include_dirs_applied)
        for extra in result.extras_included:
            if extra not in included_dirs_for_wrapper:
                included_dirs_for_wrapper.append(extra)

        wrapper_skill = generate_wrapper_skill(
            wrapper_name=record.wrapper_name,
            plugin_name=record.plugin_name,
            source_path=source_root,
            included_dirs=included_dirs_for_wrapper,
        )
        (staged_wrapper / "SKILL.md").write_text(wrapper_skill, encoding="utf-8")

        agents_dir = staged_wrapper / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "openai.yaml").write_text(
            generate_openai_yaml(record.wrapper_name, record.plugin_name),
            encoding="utf-8",
        )

        destination_wrapper = codex_skills_root / record.wrapper_name
        result.target_path = str(destination_wrapper)
        if dry_run:
            result.status = "dry-run"
        else:
            deploy_directory(staged_wrapper, destination_wrapper, backup_root)
            result.status = "ok"

        if sync_prompts_mode != "none":
            commands_dir = resolve_include_source_dir(source_root, "commands")
            if commands_dir is None:
                result.warnings.append(format_missing_include_warning(source_root, "commands"))
                commands_dir = source_root / "commands"
            if sync_prompts_mode in {"project", "both"}:
                sync_prompts_from_commands(
                    source_commands_dir=commands_dir,
                    prompts_root=project_prompts_root,
                    dry_run=dry_run,
                    result=result,
                    prompt_args_token=prompt_args_token,
                )
            if sync_prompts_mode in {"global", "both"}:
                sync_prompts_from_commands(
                    source_commands_dir=commands_dir,
                    prompts_root=global_prompts_root,
                    dry_run=dry_run,
                    result=result,
                    prompt_args_token=prompt_args_token,
                )
    except Exception as error:
        result.status = "error"
        result.error = str(error)
    finally:
        if tmp_root.exists():
            shutil.rmtree(tmp_root, ignore_errors=True)

    return result


def sync_plugin_to_codex_plugin(
    record: PluginRecord,
    source_root: Path,
    codex_plugins_root: Path,
    extra_dirs_mode: str,
    placeholder_mode: str,
    hook_event_map_mode: str,
    dry_run: bool,
    backup_root: Path,
    sync_prompts_mode: str,
    prompt_args_token: str,
    project_prompts_root: Path,
    global_prompts_root: Path,
) -> PluginResult:
    requested_dirs = list(record.include_dirs) if record.include_dirs else list(SUPPORTED_INCLUDE_DIRS)
    result = PluginResult(
        wrapper_name=record.wrapper_name,
        plugin_name=record.plugin_name,
        source_selected=str(source_root),
        include_dirs_requested=requested_dirs,
    )

    tmp_root = Path(tempfile.mkdtemp(prefix="codex-plugin-sync-"))
    staged_plugin = tmp_root / record.plugin_name

    include_mapping = {
        "skills": Path("skills"),
        "commands": Path("commands"),
        "agents": Path("agents"),
    }

    try:
        staged_plugin.mkdir(parents=True, exist_ok=True)

        for include_dir in requested_dirs:
            if include_dir not in include_mapping:
                result.warnings.append(f"Unsupported include dir in manifest: {include_dir}")
                continue
            source_dir = resolve_include_source_dir(source_root, include_dir)
            if source_dir is None:
                result.warnings.append(format_missing_include_warning(source_root, include_dir))
                continue
            target_dir = staged_plugin / include_mapping[include_dir]
            copy_directory(source_dir, target_dir)
            result.include_dirs_applied.append(include_dir)

        include_extras = extra_dirs_mode != "never"
        if include_extras:
            for extra_dir in ("hooks", "scripts"):
                source_extra = source_root / extra_dir
                if not source_extra.is_dir():
                    continue
                target_extra = staged_plugin / extra_dir
                copy_directory(source_extra, target_extra)
                result.extras_included.append(extra_dir)

        for optional_dir in OPTIONAL_PLUGIN_DIRS:
            source_optional = source_root / optional_dir
            if source_optional.is_dir():
                copy_directory(source_optional, staged_plugin / optional_dir)

        for optional_file in (".mcp.json", ".app.json", "mcp.json", "app.json"):
            source_optional_file = source_root / optional_file
            if source_optional_file.is_file():
                shutil.copy2(source_optional_file, staged_plugin / optional_file)

        for file_path in staged_plugin.rglob("*"):
            if not file_path.is_file():
                continue
            process_text_file(
                file_path=file_path,
                wrapper_root=staged_plugin,
                placeholder_mode=placeholder_mode,
                hook_event_map_mode=hook_event_map_mode,
                placeholder_replacement=f"${{CODEX_HOME:-$HOME/.codex}}/plugins/{record.plugin_name}",
                result=result,
                apply_frontmatter=True,
            )

        source_manifest = read_source_plugin_manifest(source_root)
        codex_manifest = build_codex_plugin_manifest(
            plugin_name=record.plugin_name,
            source_manifest=source_manifest,
            staged_plugin=staged_plugin,
            include_dirs=result.include_dirs_applied,
            extras_included=result.extras_included,
        )
        codex_manifest_path = staged_plugin / ".codex-plugin" / "plugin.json"
        codex_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        codex_manifest_path.write_text(
            json.dumps(codex_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        destination_plugin = codex_plugins_root / record.plugin_name
        result.target_path = str(destination_plugin)
        if dry_run:
            result.status = "dry-run"
        else:
            deploy_directory(staged_plugin, destination_plugin, backup_root)
            result.status = "ok"

        if sync_prompts_mode != "none":
            commands_dir = resolve_include_source_dir(source_root, "commands")
            if commands_dir is None:
                result.warnings.append(format_missing_include_warning(source_root, "commands"))
                commands_dir = source_root / "commands"
            if sync_prompts_mode in {"project", "both"}:
                sync_prompts_from_commands(
                    source_commands_dir=commands_dir,
                    prompts_root=project_prompts_root,
                    dry_run=dry_run,
                    result=result,
                    prompt_args_token=prompt_args_token,
                )
            if sync_prompts_mode in {"global", "both"}:
                sync_prompts_from_commands(
                    source_commands_dir=commands_dir,
                    prompts_root=global_prompts_root,
                    dry_run=dry_run,
                    result=result,
                    prompt_args_token=prompt_args_token,
                )
    except Exception as error:
        result.status = "error"
        result.error = str(error)
    finally:
        if tmp_root.exists():
            shutil.rmtree(tmp_root, ignore_errors=True)

    return result


def print_plugin_summary(result: PluginResult) -> None:
    dirs = ",".join(result.include_dirs_applied) or "-"
    extras = ",".join(result.extras_included) or "-"
    source = result.source_selected or "-"
    target = result.target_path or "-"
    status = result.status.upper()
    print(
        f"[{status}] {result.wrapper_name} | source={source} | target={target} | dirs={dirs} | extras={extras} | "
        f"converted={result.stats.files_converted} | removed={result.stats.fields_removed} | "
        f"added={result.stats.fields_added} | rewrites={result.stats.placeholder_rewrites} | "
        f"hook_maps={result.stats.hook_events_mapped} | "
        f"prompts={result.stats.prompts_synced}"
    )
    for warning in result.warnings:
        print(f"  warning: {warning}")
    if result.error:
        print(f"  error: {result.error}")


def build_report(args: argparse.Namespace, results: list[PluginResult]) -> dict:
    ok_count = sum(1 for result in results if result.status in {"ok", "dry-run"})
    skipped_count = sum(1 for result in results if result.status == "skipped")
    error_count = sum(1 for result in results if result.status == "error")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "plugins": args.plugins,
            "record_source": args.record_source,
            "manifest": str(Path(args.manifest).expanduser()),
            "workspace_plugins": str(Path(args.workspace_plugins).expanduser()),
            "output_mode": args.output_mode,
            "codex_skills_root": str(Path(args.codex_skills_root).expanduser()),
            "codex_plugins_root": str(Path(args.codex_plugins_root).expanduser()),
            "source_policy": args.source_policy,
            "missing_source_policy": args.missing_source_policy,
            "extra_dirs": args.extra_dirs,
            "placeholder_mode": args.placeholder_mode,
            "hook_event_map": args.hook_event_map,
            "dry_run": args.dry_run,
            "sync_prompts": args.sync_prompts,
            "prompt_args_token": args.prompt_args_token,
            "project_root": str(Path(args.project_root).expanduser()),
            "global_prompts_root": str(Path(args.global_prompts_root).expanduser()),
        },
        "summary": {
            "total": len(results),
            "ok": ok_count,
            "skipped": skipped_count,
            "error": error_count,
        },
        "plugins": [
            {
                "wrapper_name": result.wrapper_name,
                "plugin_name": result.plugin_name,
                "status": result.status,
                "source_selected": result.source_selected,
                "source_origin": result.source_origin,
                "target_path": result.target_path,
                "include_dirs_requested": result.include_dirs_requested,
                "include_dirs_applied": result.include_dirs_applied,
                "extras_included": result.extras_included,
                "warnings": result.warnings,
                "error": result.error,
                "stats": {
                    "files_processed": result.stats.files_processed,
                    "files_converted": result.stats.files_converted,
                    "fields_removed": result.stats.fields_removed,
                    "fields_added": result.stats.fields_added,
                    "placeholder_hits": result.stats.placeholder_hits,
                    "placeholder_rewrites": result.stats.placeholder_rewrites,
                    "hook_events_mapped": result.stats.hook_events_mapped,
                    "prompts_synced": result.stats.prompts_synced,
                },
            }
            for result in results
        ],
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    prompt_args_token = args.prompt_args_token.strip()
    if not prompt_args_token:
        print("Error: --prompt-args-token cannot be empty", file=sys.stderr)
        return 1

    manifest_path = Path(args.manifest).expanduser()
    workspace_plugins = Path(args.workspace_plugins).expanduser()
    codex_skills_root = Path(args.codex_skills_root).expanduser()
    codex_plugins_root = Path(args.codex_plugins_root).expanduser()
    project_root = Path(args.project_root).expanduser()
    project_prompts_root = project_root / ".codex" / "prompts"
    global_prompts_root = Path(args.global_prompts_root).expanduser()

    if args.record_source == "auto":
        resolved_record_source = "workspace" if args.output_mode == "codex-plugin" else "manifest"
    else:
        resolved_record_source = args.record_source

    try:
        if resolved_record_source == "manifest":
            records = load_manifest(manifest_path)
            try:
                selected = select_records(records, args.plugins)
            except ValueError:
                if args.record_source != "auto":
                    raise
                records = load_workspace_records(workspace_plugins)
                selected = select_records(records, args.plugins)
                resolved_record_source = "workspace"
        else:
            records = load_workspace_records(workspace_plugins)
            selected = select_records(records, args.plugins)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if args.output_mode == "wrapper-skill":
        output_root = codex_skills_root
    else:
        output_root = codex_plugins_root

    if not args.dry_run:
        output_root.mkdir(parents=True, exist_ok=True)
    backup_root = output_root / ".sync-backups" / datetime.now().strftime("%Y%m%d-%H%M%S")

    results: list[PluginResult] = []

    for record in selected:
        try:
            source_root, source_origin = resolve_source(
                record=record,
                workspace_plugins=workspace_plugins,
                source_policy=args.source_policy,
            )
            if args.output_mode == "wrapper-skill":
                result = sync_plugin(
                    record=record,
                    source_root=source_root,
                    codex_skills_root=codex_skills_root,
                    extra_dirs_mode=args.extra_dirs,
                    placeholder_mode=args.placeholder_mode,
                    hook_event_map_mode=args.hook_event_map,
                    dry_run=args.dry_run,
                    backup_root=backup_root,
                    sync_prompts_mode=args.sync_prompts,
                    prompt_args_token=prompt_args_token,
                    project_prompts_root=project_prompts_root,
                    global_prompts_root=global_prompts_root,
                )
            else:
                result = sync_plugin_to_codex_plugin(
                    record=record,
                    source_root=source_root,
                    codex_plugins_root=codex_plugins_root,
                    extra_dirs_mode=args.extra_dirs,
                    placeholder_mode=args.placeholder_mode,
                    hook_event_map_mode=args.hook_event_map,
                    dry_run=args.dry_run,
                    backup_root=backup_root,
                    sync_prompts_mode=args.sync_prompts,
                    prompt_args_token=prompt_args_token,
                    project_prompts_root=project_prompts_root,
                    global_prompts_root=global_prompts_root,
                )
            result.source_origin = source_origin
        except FileNotFoundError as error:
            if args.missing_source_policy == "skip":
                result = PluginResult(
                    wrapper_name=record.wrapper_name,
                    plugin_name=record.plugin_name,
                    source_selected=str(record.source),
                    source_origin=None,
                    include_dirs_requested=list(record.include_dirs),
                    status="skipped",
                )
                result.warnings.append(str(error))
            else:
                result = PluginResult(
                    wrapper_name=record.wrapper_name,
                    plugin_name=record.plugin_name,
                    source_selected=str(record.source),
                    source_origin=None,
                    include_dirs_requested=list(record.include_dirs),
                    status="error",
                    error=str(error),
                )
        except Exception as error:
            result = PluginResult(
                wrapper_name=record.wrapper_name,
                plugin_name=record.plugin_name,
                source_selected=str(record.source),
                source_origin=None,
                include_dirs_requested=list(record.include_dirs),
                status="error",
                error=str(error),
            )
        results.append(result)
        print_plugin_summary(result)

    report = build_report(args, results)
    if args.report:
        report_path = Path(args.report).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Report written: {report_path}")

    return 1 if any(result.status == "error" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
