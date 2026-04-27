from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class FailureType(str, Enum):
    SQL_SYNTAX_ERROR = "sql_syntax_error"
    RELATION_NOT_FOUND = "relation_not_found"
    DEPENDENCY_FAILURE = "dependency_failure"
    DATA_QUALITY_TEST = "data_quality_test"
    SOURCE_FRESHNESS = "source_freshness"
    PERMISSION_DENIED = "permission_denied"
    CONFIG_ERROR = "config_error"
    COMPILATION_ERROR = "compilation_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# dbt Artifact Models
# ---------------------------------------------------------------------------

class DbtNodeDependsOn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nodes: list[str] = []
    macros: list[str] = []


class DbtNodeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    materialized: Optional[str] = None
    schema_: Optional[str] = Field(None, alias="schema")
    tags: list[str] = []
    meta: dict[str, Any] = {}


class DbtNode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    unique_id: str
    name: str
    resource_type: str
    path: Optional[str] = None
    original_file_path: Optional[str] = None
    fqn: list[str] = []
    depends_on: DbtNodeDependsOn = Field(default_factory=DbtNodeDependsOn)
    refs: list[Any] = []
    sources: list[Any] = []
    config: Optional[DbtNodeConfig] = None
    description: Optional[str] = None
    raw_code: Optional[str] = None
    compiled_code: Optional[str] = None
    test_metadata: Optional[dict[str, Any]] = None
    attached_node: Optional[str] = None
    columns: dict[str, Any] = {}


class DbtSource(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    unique_id: str
    name: str
    source_name: Optional[str] = None
    schema_: Optional[str] = Field(None, alias="schema")
    database: Optional[str] = None
    loaded_at_field: Optional[str] = None
    freshness: Optional[dict[str, Any]] = None


class DbtManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    metadata: dict[str, Any] = {}
    nodes: dict[str, DbtNode] = {}
    sources: dict[str, DbtSource] = {}
    parent_map: dict[str, list[str]] = {}
    child_map: dict[str, list[str]] = {}

    @classmethod
    def from_path(cls, path: str | Path) -> "DbtManifest":
        return cls.model_validate(json.loads(Path(path).read_text()))

    def get_node(self, unique_id: str) -> Optional[DbtNode]:
        return self.nodes.get(unique_id) or self.sources.get(unique_id)  # type: ignore[return-value]

    def get_upstream(self, unique_id: str) -> list[str]:
        node = self.nodes.get(unique_id)
        if node:
            return node.depends_on.nodes
        return self.parent_map.get(unique_id, [])

    def get_downstream(self, unique_id: str) -> list[str]:
        return self.child_map.get(unique_id, [])


class DbtRunResultNode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    unique_id: str
    status: str
    execution_time: Optional[float] = None
    failures: Optional[int] = None
    message: Optional[str] = None
    thread_id: Optional[str] = None
    timing: list[dict[str, Any]] = []
    adapter_response: dict[str, Any] = {}
    compiled_code: Optional[str] = None


class DbtRunResults(BaseModel):
    model_config = ConfigDict(extra="ignore")
    metadata: dict[str, Any] = {}
    elapsed_time: Optional[float] = None
    results: list[DbtRunResultNode] = []
    args: dict[str, Any] = {}

    @classmethod
    def from_path(cls, path: str | Path) -> "DbtRunResults":
        return cls.model_validate(json.loads(Path(path).read_text()))

    def get_failures(self) -> list[DbtRunResultNode]:
        return [r for r in self.results if r.status in ("error", "fail")]

    def get_skipped(self) -> list[DbtRunResultNode]:
        return [r for r in self.results if r.status == "skipped"]


# ---------------------------------------------------------------------------
# Agent I/O Models
# ---------------------------------------------------------------------------

class TriageInput(BaseModel):
    # Paths on disk — passed directly to tools
    run_results_path: str
    manifest_path: Optional[str] = None
    # Pre-parsed artifacts (loaded by CLI before constructing this object)
    run_results: DbtRunResults
    dbt_log: str = ""
    manifest: Optional[DbtManifest] = None
    project_name: Optional[str] = None
    target: Optional[str] = None


class RemediationStep(BaseModel):
    step: int
    action: str
    command: Optional[str] = None
    rationale: str


class TriageReport(BaseModel):
    failure_type: str
    severity: str
    root_cause: str
    affected_models: list[str] = []
    upstream_cause: Optional[str] = None
    remediation_steps: list[RemediationStep] = []
    generated_fix: Optional[str] = None
    investigation_summary: str = ""
    confidence: float = 0.0

    def to_markdown(self) -> str:
        lines = [
            f"# dbt Pipeline Triage Report",
            f"",
            f"**Failure Type:** `{self.failure_type}`  ",
            f"**Severity:** `{self.severity}`  ",
            f"**Confidence:** {int(self.confidence * 100)}%",
            f"",
            f"## Root Cause",
            f"",
            self.root_cause,
            f"",
        ]
        if self.upstream_cause:
            lines += [f"**Upstream Cause:** `{self.upstream_cause}`", ""]
        if self.affected_models:
            lines += ["## Affected Models", ""]
            for m in self.affected_models:
                lines.append(f"- `{m}`")
            lines.append("")
        if self.remediation_steps:
            lines += ["## Remediation Steps", ""]
            for s in self.remediation_steps:
                lines.append(f"### Step {s.step}: {s.action}")
                if s.command:
                    lines.append(f"```bash\n{s.command}\n```")
                lines.append(f"_{s.rationale}_")
                lines.append("")
        if self.generated_fix:
            lines += ["## Generated Fix", "", "```sql", self.generated_fix, "```", ""]
        if self.investigation_summary:
            lines += ["## Investigation Summary", "", self.investigation_summary, ""]
        return "\n".join(lines)
