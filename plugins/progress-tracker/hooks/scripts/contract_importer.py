#!/usr/bin/env python3
"""Deterministic contract importer with JSON/Markdown FSM parsing."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


MAX_CONTRACT_FILE_BYTES = 64 * 1024
MAX_CONTRACT_LINE_LENGTH = 1024
MAX_PARSE_STEPS = 20000
MAX_PARSE_SECONDS = 0.2

LEVEL2_SECTION_REQUIREMENTS = "requirements"
LEVEL2_SECTION_CHANGES = "changes"
LEVEL2_SECTION_ACCEPTANCE = "acceptance_scenarios"

LEVEL3_CHANGE_WHY = "why"
LEVEL3_CHANGE_IN_SCOPE = "in_scope"
LEVEL3_CHANGE_OUT_OF_SCOPE = "out_of_scope"
LEVEL3_CHANGE_RISKS = "risks"

ALLOWED_LEVEL2_HEADERS = {
    "requirements": LEVEL2_SECTION_REQUIREMENTS,
    "changes": LEVEL2_SECTION_CHANGES,
    "acceptance scenarios": LEVEL2_SECTION_ACCEPTANCE,
}
ALLOWED_LEVEL3_HEADERS = {
    "why": LEVEL3_CHANGE_WHY,
    "in scope": LEVEL3_CHANGE_IN_SCOPE,
    "out of scope": LEVEL3_CHANGE_OUT_OF_SCOPE,
    "risks": LEVEL3_CHANGE_RISKS,
}


class ContractImportError(ValueError):
    """Raised when a contract file is invalid or cannot be imported safely."""


class MarkdownFSMParser:
    """Parse markdown contract format using a strict finite-state workflow."""

    def __init__(
        self,
        *,
        source: str = "<unknown>",
        max_file_bytes: int = MAX_CONTRACT_FILE_BYTES,
        max_line_length: int = MAX_CONTRACT_LINE_LENGTH,
        max_steps: int = MAX_PARSE_STEPS,
        max_seconds: float = MAX_PARSE_SECONDS,
    ) -> None:
        self.source = source
        self.max_file_bytes = max_file_bytes
        self.max_line_length = max_line_length
        self.max_steps = max_steps
        self.max_seconds = max_seconds
        self._steps = 0
        self._started_at = 0.0

    def _error(self, message: str, line_no: Optional[int] = None) -> ContractImportError:
        if line_no is None:
            return ContractImportError(f"{self.source}: {message}")
        return ContractImportError(f"{self.source}:{line_no}: {message}")

    def parse(self, content: str) -> Dict[str, Any]:
        """Parse markdown contract into canonical contract payload."""
        payload_size = len(content.encode("utf-8"))
        if payload_size > self.max_file_bytes:
            raise self._error(
                f"Contract file too large ({payload_size} bytes > {self.max_file_bytes} bytes)."
            )

        self._steps = 0
        self._started_at = time.monotonic()

        state: Dict[str, Any] = {
            "feature_heading_seen": False,
            "active_level2": None,
            "active_change_level3": None,
            "seen_level2": set(),
            "seen_level3": set(),
            "requirement_ids": [],
            "change_why_lines": [],
            "change_in_scope": [],
            "change_out_of_scope": [],
            "change_risks": [],
            "acceptance_scenarios": [],
        }

        for line_no, raw_line in enumerate(content.splitlines(), start=1):
            self._consume_budget()
            if len(raw_line) > self.max_line_length:
                raise self._error(
                    f"line exceeds max length {self.max_line_length}.",
                    line_no=line_no,
                )

            stripped = raw_line.strip()
            if not stripped:
                if (
                    state["active_level2"] == LEVEL2_SECTION_CHANGES
                    and state["active_change_level3"] == LEVEL3_CHANGE_WHY
                    and state["change_why_lines"]
                    and state["change_why_lines"][-1] != ""
                ):
                    state["change_why_lines"].append("")
                continue

            if stripped.startswith("#"):
                self._consume_budget()
                self._transition_heading(state, stripped, line_no)
                continue

            if stripped.startswith("- "):
                self._consume_budget()
                item = stripped[2:].strip()
                if not item:
                    raise self._error("empty list item is not allowed.", line_no=line_no)
                self._consume_bullet(state, item, line_no)
                continue

            self._consume_text(state, stripped, line_no)

        return self._finalize(state)

    def _consume_budget(self) -> None:
        self._steps += 1
        if self._steps > self.max_steps:
            raise self._error(f"Parsing budget exceeded ({self.max_steps} steps).")
        if (time.monotonic() - self._started_at) > self.max_seconds:
            raise self._error(f"Parsing time budget exceeded ({self.max_seconds:.3f}s).")

    def _transition_heading(self, state: Dict[str, Any], line: str, line_no: int) -> None:
        level, heading = self._parse_heading_line(line, line_no)

        if level == 1:
            if not heading.lower().startswith("feature:"):
                raise self._error(
                    "level-1 heading must start with 'Feature:'.",
                    line_no=line_no,
                )
            feature_name = heading.split(":", 1)[1].strip()
            if not feature_name:
                raise self._error("feature name cannot be empty.", line_no=line_no)
            state["feature_heading_seen"] = True
            state["active_level2"] = None
            state["active_change_level3"] = None
            return

        if level == 2:
            section_key = ALLOWED_LEVEL2_HEADERS.get(heading.lower())
            if section_key is None:
                raise self._error(
                    f"unsupported section '{heading}'.",
                    line_no=line_no,
                )
            if section_key in state["seen_level2"]:
                raise self._error(
                    f"duplicate section '{heading}'.",
                    line_no=line_no,
                )
            state["seen_level2"].add(section_key)
            state["active_level2"] = section_key
            state["active_change_level3"] = None
            return

        # level == 3 here
        if state["active_level2"] != LEVEL2_SECTION_CHANGES:
            raise self._error(
                "level-3 heading is only valid under '## Changes'.",
                line_no=line_no,
            )
        subsection_key = ALLOWED_LEVEL3_HEADERS.get(heading.lower())
        if subsection_key is None:
            raise self._error(
                f"unsupported Changes subsection '{heading}'.",
                line_no=line_no,
            )
        if subsection_key in state["seen_level3"]:
            raise self._error(
                f"duplicate Changes subsection '{heading}'.",
                line_no=line_no,
            )
        state["seen_level3"].add(subsection_key)
        state["active_change_level3"] = subsection_key

    def _parse_heading_line(self, line: str, line_no: int) -> tuple[int, str]:
        index = 0
        while index < len(line) and line[index] == "#":
            index += 1

        level = index
        if level < 1 or level > 3:
            raise self._error(
                "heading depth must be 1-3 levels (#/##/###).",
                line_no=line_no,
            )
        if index >= len(line) or line[index] != " ":
            raise self._error(
                "heading must contain a space after '#'.",
                line_no=line_no,
            )

        heading = line[index + 1 :].strip()
        if not heading:
            raise self._error("heading text cannot be empty.", line_no=line_no)
        return level, heading

    def _consume_bullet(self, state: Dict[str, Any], item: str, line_no: int) -> None:
        level2 = state["active_level2"]
        if level2 == LEVEL2_SECTION_REQUIREMENTS:
            try:
                req_id = ContractImporter.parse_requirement_id(item)
            except ContractImportError as exc:
                raise self._error(str(exc), line_no=line_no) from exc
            if req_id not in state["requirement_ids"]:
                state["requirement_ids"].append(req_id)
            return

        if level2 == LEVEL2_SECTION_ACCEPTANCE:
            scenario = item
            if not scenario.lower().startswith("scenario:"):
                scenario = f"Scenario: {scenario}"
            state["acceptance_scenarios"].append(scenario)
            return

        if level2 == LEVEL2_SECTION_CHANGES:
            level3 = state["active_change_level3"]
            if level3 == LEVEL3_CHANGE_IN_SCOPE:
                state["change_in_scope"].append(item)
                return
            if level3 == LEVEL3_CHANGE_OUT_OF_SCOPE:
                state["change_out_of_scope"].append(item)
                return
            if level3 == LEVEL3_CHANGE_RISKS:
                state["change_risks"].append(item)
                return
            if level3 == LEVEL3_CHANGE_WHY:
                state["change_why_lines"].append(item)
                return

        raise self._error(
            "list item appears outside an allowed section.",
            line_no=line_no,
        )

    def _consume_text(self, state: Dict[str, Any], text: str, line_no: int) -> None:
        if (
            state["active_level2"] == LEVEL2_SECTION_CHANGES
            and state["active_change_level3"] == LEVEL3_CHANGE_WHY
        ):
            state["change_why_lines"].append(text)
            return

        raise self._error(
            "free text is only allowed under '### Why'.",
            line_no=line_no,
        )

    @staticmethod
    def _compact_lines(lines: List[str]) -> str:
        start = 0
        end = len(lines)
        while start < end and lines[start] == "":
            start += 1
        while end > start and lines[end - 1] == "":
            end -= 1
        return "\n".join(lines[start:end]).strip()

    def _finalize(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if not state["feature_heading_seen"]:
            raise self._error("Missing '# Feature: <name>' heading.")

        required_level2 = {
            LEVEL2_SECTION_REQUIREMENTS,
            LEVEL2_SECTION_CHANGES,
            LEVEL2_SECTION_ACCEPTANCE,
        }
        missing_level2 = required_level2 - set(state["seen_level2"])
        if missing_level2:
            missing = ", ".join(sorted(missing_level2))
            raise self._error(f"Missing required section(s): {missing}.")

        required_level3 = {
            LEVEL3_CHANGE_WHY,
            LEVEL3_CHANGE_IN_SCOPE,
            LEVEL3_CHANGE_OUT_OF_SCOPE,
            LEVEL3_CHANGE_RISKS,
        }
        missing_level3 = required_level3 - set(state["seen_level3"])
        if missing_level3:
            missing = ", ".join(sorted(missing_level3))
            raise self._error(f"Missing required Changes subsection(s): {missing}.")

        why_text = self._compact_lines(state["change_why_lines"])
        payload = {
            "requirement_ids": state["requirement_ids"],
            "change_spec": {
                "why": why_text,
                "in_scope": state["change_in_scope"],
                "out_of_scope": state["change_out_of_scope"],
                "risks": state["change_risks"],
            },
            "acceptance_scenarios": state["acceptance_scenarios"],
        }
        return ContractImporter.normalize_contract_payload(payload)


class ContractImporter:
    """Resolve and import feature contracts from deterministic file locations."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self.contracts_dir = self.project_root / "docs" / "progress-tracker" / "contracts"

    def import_for_feature(self, feature_id: int) -> Optional[Dict[str, Any]]:
        """Return canonical contract payload for feature, or None when file is absent."""
        path = self._find_contract_file(feature_id)
        if path is None:
            return None

        if path.suffix == ".json":
            return self._parse_json(path)
        if path.suffix == ".md":
            return self._parse_markdown(path)

        raise ContractImportError(f"Unsupported contract extension for {path.name}.")

    def _find_contract_file(self, feature_id: int) -> Optional[Path]:
        if not self.contracts_dir.exists():
            return None

        json_path = self.contracts_dir / f"feature-{feature_id}.json"
        md_path = self.contracts_dir / f"feature-{feature_id}.md"

        json_exists = json_path.exists()
        md_exists = md_path.exists()
        if json_exists and md_exists:
            raise ContractImportError(
                "Ambiguous contract file: both "
                f"{json_path.name} and {md_path.name} exist."
            )
        if json_exists:
            return json_path
        if md_exists:
            return md_path
        return None

    def _parse_json(self, path: Path) -> Dict[str, Any]:
        content = path.read_text(encoding="utf-8")
        payload_size = len(content.encode("utf-8"))
        if payload_size > MAX_CONTRACT_FILE_BYTES:
            raise ContractImportError(
                f"Contract file too large ({payload_size} bytes > {MAX_CONTRACT_FILE_BYTES} bytes)."
            )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ContractImportError(
                f"Invalid JSON contract in {path.name}: {exc.msg}"
            ) from exc
        return self.normalize_contract_payload(payload)

    def _parse_markdown(self, path: Path) -> Dict[str, Any]:
        content = path.read_text(encoding="utf-8")
        parser = MarkdownFSMParser(source=path.as_posix())
        return parser.parse(content)

    @staticmethod
    def parse_requirement_id(text: str) -> str:
        req_id = text.split(":", 1)[0].strip().upper()
        if not req_id.startswith("REQ-"):
            raise ContractImportError(f"Invalid requirement ID: {text}")
        return req_id

    @staticmethod
    def normalize_contract_payload(payload: Any) -> Dict[str, Any]:
        """Validate and normalize imported payload to schema contract fields."""
        if not isinstance(payload, dict):
            raise ContractImportError("Contract payload must be a JSON object.")

        requirement_ids = ContractImporter._normalize_requirement_ids(
            payload.get("requirement_ids")
        )

        change_spec_raw = payload.get("change_spec")
        if not isinstance(change_spec_raw, dict):
            raise ContractImportError("Contract field 'change_spec' must be an object.")

        change_spec = {
            "why": ContractImporter._normalize_non_empty_string(
                change_spec_raw.get("why"),
                field_name="change_spec.why",
            ),
            "in_scope": ContractImporter._normalize_non_empty_string_list(
                change_spec_raw.get("in_scope"),
                field_name="change_spec.in_scope",
            ),
            "out_of_scope": ContractImporter._normalize_non_empty_string_list(
                change_spec_raw.get("out_of_scope"),
                field_name="change_spec.out_of_scope",
            ),
            "risks": ContractImporter._normalize_non_empty_string_list(
                change_spec_raw.get("risks"),
                field_name="change_spec.risks",
            ),
        }

        acceptance_scenarios = ContractImporter._normalize_non_empty_string_list(
            payload.get("acceptance_scenarios"),
            field_name="acceptance_scenarios",
        )
        acceptance_scenarios = [
            item if item.lower().startswith("scenario:") else f"Scenario: {item}"
            for item in acceptance_scenarios
        ]

        return {
            "requirement_ids": requirement_ids,
            "change_spec": change_spec,
            "acceptance_scenarios": acceptance_scenarios,
        }

    @staticmethod
    def _normalize_requirement_ids(value: Any) -> List[str]:
        values = ContractImporter._normalize_non_empty_string_list(
            value, field_name="requirement_ids"
        )
        deduped: List[str] = []
        for raw_item in values:
            req_id = ContractImporter.parse_requirement_id(raw_item)
            if req_id not in deduped:
                deduped.append(req_id)
        return deduped

    @staticmethod
    def _normalize_non_empty_string(value: Any, *, field_name: str) -> str:
        if not isinstance(value, str):
            raise ContractImportError(f"Contract field '{field_name}' must be a string.")
        normalized = value.strip()
        if not normalized:
            raise ContractImportError(f"Contract field '{field_name}' cannot be empty.")
        return normalized

    @staticmethod
    def _normalize_non_empty_string_list(value: Any, *, field_name: str) -> List[str]:
        if not isinstance(value, list):
            raise ContractImportError(f"Contract field '{field_name}' must be a list.")
        normalized_items: List[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ContractImportError(
                    f"Contract field '{field_name}' must contain only strings."
                )
            normalized = item.strip()
            if normalized:
                normalized_items.append(normalized)
        if not normalized_items:
            raise ContractImportError(
                f"Contract field '{field_name}' must contain at least one non-empty item."
            )
        return normalized_items
