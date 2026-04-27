"""
Tool implementations for the dbt triage agent.

Each public function maps 1-to-1 with a tool schema in tool_schemas.py.
All functions are pure: they read files and return JSON-serializable dicts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text())


# ---------------------------------------------------------------------------
# Tool: list_failed_nodes
# ---------------------------------------------------------------------------

def list_failed_nodes(run_results_path: str) -> dict:
    """Return all failed/errored nodes from run_results.json."""
    data = _load_json(run_results_path)
    results = data.get("results", [])
    failures = []
    skipped = []

    for r in results:
        status = r.get("status", "")
        if status in ("error", "fail"):
            failures.append({
                "node_id": r.get("unique_id", ""),
                "status": status,
                "error_message": r.get("message", ""),
                "execution_time_sec": r.get("execution_time"),
            })
        elif status == "skipped":
            skipped.append(r.get("unique_id", ""))

    return {
        "total_results": len(results),
        "failed_count": len(failures),
        "skipped_count": len(skipped),
        "elapsed_time_sec": data.get("elapsed_time"),
        "dbt_version": data.get("metadata", {}).get("dbt_schema_version", ""),
        "failures": failures,
        "skipped_node_ids": skipped,
    }


# ---------------------------------------------------------------------------
# Tool: get_model_sql
# ---------------------------------------------------------------------------

def get_model_sql(manifest_path: str, node_id: str, sql_type: str = "raw") -> dict:
    """Return the SQL source for a model node."""
    manifest = _load_json(manifest_path)
    node = manifest.get("nodes", {}).get(node_id)
    if not node:
        node = manifest.get("sources", {}).get(node_id)
    if not node:
        return {"error": f"Node '{node_id}' not found in manifest"}

    if sql_type == "compiled":
        sql = node.get("compiled_code") or node.get("compiled_sql") or ""
    else:
        sql = node.get("raw_code") or node.get("raw_sql") or ""

    return {
        "node_id": node_id,
        "name": node.get("name", ""),
        "sql_type": sql_type,
        "path": node.get("original_file_path", ""),
        "sql": sql,
    }


# ---------------------------------------------------------------------------
# Tool: get_model_dependencies
# ---------------------------------------------------------------------------

def get_model_dependencies(manifest_path: str, node_id: str) -> dict:
    """Return upstream and downstream dependency lists for a node."""
    manifest = _load_json(manifest_path)
    node = manifest.get("nodes", {}).get(node_id, {})

    upstream: list[str] = (
        node.get("depends_on", {}).get("nodes", [])
        or manifest.get("parent_map", {}).get(node_id, [])
    )
    downstream: list[str] = manifest.get("child_map", {}).get(node_id, [])

    def _name(uid: str) -> str:
        n = manifest.get("nodes", {}).get(uid, {})
        return n.get("name", uid)

    return {
        "node_id": node_id,
        "name": node.get("name", node_id),
        "upstream": [{"node_id": u, "name": _name(u)} for u in upstream],
        "downstream": [{"node_id": d, "name": _name(d)} for d in downstream],
        "upstream_count": len(upstream),
        "downstream_count": len(downstream),
    }


# ---------------------------------------------------------------------------
# Tool: check_ref_resolution
# ---------------------------------------------------------------------------

def check_ref_resolution(manifest_path: str, node_id: str) -> dict:
    """Check whether all ref() calls in a model resolve to known manifest nodes."""
    manifest = _load_json(manifest_path)
    node = manifest.get("nodes", {}).get(node_id)
    if not node:
        return {"error": f"Node '{node_id}' not found in manifest"}

    raw_sql = node.get("raw_code") or node.get("raw_sql") or ""

    # Extract all ref() calls: {{ ref('model_name') }} or {{ ref("model_name") }}
    ref_pattern = re.compile(r"""{{\s*ref\(\s*['"]([^'"]+)['"]\s*\)\s*}}""")
    referenced_names = ref_pattern.findall(raw_sql)

    # Build set of all model names in manifest
    known_names = {
        v.get("name", "") for v in manifest.get("nodes", {}).values()
    }

    unresolved = []
    resolved = []
    for name in set(referenced_names):
        if name in known_names:
            resolved.append(name)
        else:
            # Find close matches (simple Levenshtein-like suggestions)
            suggestions = _find_similar_names(name, known_names)
            unresolved.append({
                "ref_name": name,
                "suggestions": suggestions[:3],
            })

    return {
        "node_id": node_id,
        "total_refs": len(set(referenced_names)),
        "resolved": resolved,
        "unresolved": unresolved,
        "has_broken_refs": len(unresolved) > 0,
    }


def _find_similar_names(target: str, candidates: set[str], max_dist: int = 3) -> list[str]:
    """Return candidates within edit distance of target (simple heuristic)."""
    target_lower = target.lower()
    results = []
    for c in sorted(candidates):
        c_lower = c.lower()
        # Prefix match or substring
        if c_lower.startswith(target_lower[:4]) or target_lower in c_lower or c_lower in target_lower:
            results.append(c)
    return results[:5]


# ---------------------------------------------------------------------------
# Tool: get_error_context
# ---------------------------------------------------------------------------

def get_error_context(manifest_path: str, run_results_path: str, node_id: str) -> dict:
    """Return the error message plus the first 60 lines of the model's raw SQL."""
    manifest = _load_json(manifest_path)
    run_results = _load_json(run_results_path)

    # Find error message in run_results
    error_msg = ""
    for r in run_results.get("results", []):
        if r.get("unique_id") == node_id:
            error_msg = r.get("message", "")
            break

    # Get SQL from manifest
    node = manifest.get("nodes", {}).get(node_id, {})
    if not node:
        return {"error": f"Node '{node_id}' not found in manifest"}

    raw_sql = node.get("raw_code") or node.get("raw_sql") or ""
    sql_preview = "\n".join(raw_sql.splitlines()[:60])

    return {
        "node_id": node_id,
        "name": node.get("name", ""),
        "path": node.get("original_file_path", ""),
        "error_message": error_msg,
        "sql_preview": sql_preview,
        "sql_line_count": len(raw_sql.splitlines()),
    }


# ---------------------------------------------------------------------------
# Dispatch registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, Any] = {
    "list_failed_nodes": lambda inp, _ctx: list_failed_nodes(**inp),
    "get_model_sql": lambda inp, _ctx: get_model_sql(**inp),
    "get_model_dependencies": lambda inp, _ctx: get_model_dependencies(**inp),
    "check_ref_resolution": lambda inp, _ctx: check_ref_resolution(**inp),
    "get_error_context": lambda inp, _ctx: get_error_context(**inp),
    # submit_triage_report is handled by the agent loop directly — not dispatched here
}
