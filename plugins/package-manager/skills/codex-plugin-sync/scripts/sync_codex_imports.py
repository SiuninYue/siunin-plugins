#!/usr/bin/env python3
"""Sync Claude plugin resources into Codex skill wrappers with compatibility transforms."""

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

SUPPORTED_INCLUDE_DIRS = ("skills", "commands", "agents")
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
    prompts_synced: int = 0


@dataclass
class PluginResult:
    wrapper_name: str
    plugin_name: str
    source_selected: str | None = None
    source_origin: str | None = None
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sync migrated Claude plugin resources into ~/.codex/skills wrappers and "
            "normalize content for Codex compatibility."
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
        default="/Users/siunin/Projects/Claude-Plugins/plugins",
        help="Workspace plugins directory for workspace-first resolution.",
    )
    parser.add_argument(
        "--codex-skills-root",
        default=str(default_codex_skills_root()),
        help="Codex skills root directory (default: $CODEX_HOME/skills).",
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
        "--dry-run",
        action="store_true",
        help="Compute and report changes without writing to codex skills.",
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
    return None, None


def has_plugin_root_placeholder(text: str) -> bool:
    return PLACEHOLDER_BRACED in text or bool(PLACEHOLDER_PLAIN_PATTERN.search(text))


def rewrite_placeholders(text: str, replacement: str) -> tuple[str, int]:
    hits = text.count(PLACEHOLDER_BRACED)
    rewritten = text.replace(PLACEHOLDER_BRACED, replacement)

    plain_hits = len(PLACEHOLDER_PLAIN_PATTERN.findall(rewritten))
    rewritten = PLACEHOLDER_PLAIN_PATTERN.sub(replacement, rewritten)
    return rewritten, hits + plain_hits


def process_text_file(
    file_path: Path,
    wrapper_root: Path,
    wrapper_name: str,
    placeholder_mode: str,
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
            replacement = f"${{CODEX_HOME:-$HOME/.codex}}/skills/{wrapper_name}"
            rewritten, rewrites = rewrite_placeholders(text, replacement)
            text = rewritten
            result.stats.placeholder_rewrites += rewrites
            changed = changed or rewrites > 0

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


def build_prompt_from_command(command_text: str, command_name: str) -> str:
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
            prompt_lines.append("If arguments are provided, treat them as extra context: `$ARGUMENTS`.")
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
        prompt_text = build_prompt_from_command(command_text, command_file.stem)
        target_file = prompts_root / prompt_name
        if not dry_run:
            target_file.write_text(prompt_text, encoding="utf-8")
        synced += 1

    result.stats.prompts_synced += synced
    return synced


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


def deploy_wrapper(
    staged_wrapper: Path,
    destination_wrapper: Path,
    backup_root: Path,
) -> None:
    destination_wrapper.parent.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / destination_wrapper.name

    moved_existing = False
    if destination_wrapper.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        if backup_path.exists():
            shutil.rmtree(backup_path)
        shutil.move(str(destination_wrapper), str(backup_path))
        moved_existing = True

    try:
        shutil.move(str(staged_wrapper), str(destination_wrapper))
    except Exception as error:
        if moved_existing and backup_path.exists() and not destination_wrapper.exists():
            shutil.move(str(backup_path), str(destination_wrapper))
        raise RuntimeError(f"Failed to deploy wrapper {destination_wrapper.name}: {error}") from error


def sync_plugin(
    record: PluginRecord,
    source_root: Path,
    codex_skills_root: Path,
    extra_dirs_mode: str,
    placeholder_mode: str,
    dry_run: bool,
    backup_root: Path,
    sync_prompts_mode: str,
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
                wrapper_name=record.wrapper_name,
                placeholder_mode=placeholder_mode,
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
                        wrapper_name=record.wrapper_name,
                        placeholder_mode=placeholder_mode,
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
        if dry_run:
            result.status = "dry-run"
        else:
            deploy_wrapper(staged_wrapper, destination_wrapper, backup_root)
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
                )
            if sync_prompts_mode in {"global", "both"}:
                sync_prompts_from_commands(
                    source_commands_dir=commands_dir,
                    prompts_root=global_prompts_root,
                    dry_run=dry_run,
                    result=result,
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
    status = result.status.upper()
    print(
        f"[{status}] {result.wrapper_name} | source={source} | dirs={dirs} | extras={extras} | "
        f"converted={result.stats.files_converted} | removed={result.stats.fields_removed} | "
        f"added={result.stats.fields_added} | rewrites={result.stats.placeholder_rewrites} | "
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
            "manifest": str(Path(args.manifest).expanduser()),
            "workspace_plugins": str(Path(args.workspace_plugins).expanduser()),
            "codex_skills_root": str(Path(args.codex_skills_root).expanduser()),
            "source_policy": args.source_policy,
            "missing_source_policy": args.missing_source_policy,
            "extra_dirs": args.extra_dirs,
            "placeholder_mode": args.placeholder_mode,
            "dry_run": args.dry_run,
            "sync_prompts": args.sync_prompts,
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
                    "prompts_synced": result.stats.prompts_synced,
                },
            }
            for result in results
        ],
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    manifest_path = Path(args.manifest).expanduser()
    workspace_plugins = Path(args.workspace_plugins).expanduser()
    codex_skills_root = Path(args.codex_skills_root).expanduser()
    project_root = Path(args.project_root).expanduser()
    project_prompts_root = project_root / ".codex" / "prompts"
    global_prompts_root = Path(args.global_prompts_root).expanduser()

    try:
        records = load_manifest(manifest_path)
        selected = select_records(records, args.plugins)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if not args.dry_run:
        codex_skills_root.mkdir(parents=True, exist_ok=True)
    backup_root = codex_skills_root / ".sync-backups" / datetime.now().strftime("%Y%m%d-%H%M%S")

    results: list[PluginResult] = []

    for record in selected:
        try:
            source_root, source_origin = resolve_source(
                record=record,
                workspace_plugins=workspace_plugins,
                source_policy=args.source_policy,
            )
            result = sync_plugin(
                record=record,
                source_root=source_root,
                codex_skills_root=codex_skills_root,
                extra_dirs_mode=args.extra_dirs,
                placeholder_mode=args.placeholder_mode,
                dry_run=args.dry_run,
                backup_root=backup_root,
                sync_prompts_mode=args.sync_prompts,
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
