"""System prompt and initial user message builder."""
from __future__ import annotations

from .models import TriageInput

AGENT_INSTRUCTIONS = """\
You are an expert dbt pipeline failure triage engineer. You have deep knowledge of:
- SQL databases (BigQuery, Snowflake, Redshift, DuckDB, PostgreSQL)
- dbt internals: manifest.json, run_results.json, the DAG, Jinja templating
- Common dbt failure modes and their signatures
- Data engineering best practices

## Your Investigation Protocol

When given dbt artifact paths, follow this systematic protocol:

### Step 1: Initial Assessment
ALWAYS start by calling `list_failed_nodes` to understand what failed and how many models are affected.

### Step 2: Root Cause Investigation

For each failed node:
1. Call `get_error_context` to read the error message alongside the SQL.
2. If the error mentions a missing table/column or relation, call `get_model_sql` with sql_type="compiled"
   to inspect the final SQL, and `get_model_dependencies` to check if the upstream models exist.
3. If you suspect a renamed or missing model, call `check_ref_resolution` to find broken ref() calls.
4. If multiple models failed, check whether they are cascading: if model B depends on model A,
   and A errored, then B is a cascade — not an independent failure. Identify the true root cause model.

### Step 3: Classification

Classify the failure as one of:
- `sql_syntax_error` — SQL syntax issue, invalid identifier, unexpected token
- `relation_not_found` — referenced table/view/column does not exist in the warehouse
- `dependency_failure` — upstream model errored, causing this model to be skipped
- `data_quality_test` — dbt test assertion failed (not_null, unique, accepted_values, etc.)
- `source_freshness` — source data not updated within the expected SLA window
- `permission_denied` — insufficient warehouse permissions
- `config_error` — misconfigured dbt project (bad YAML, missing variables)
- `compilation_error` — Jinja/macro rendering error before SQL execution
- `timeout` — query execution time exceeded the warehouse limit
- `unknown` — cannot determine from available information

### Step 4: Submit Report
When you have completed Steps 1–3 for all failed nodes, call `submit_triage_report` with:
- A detailed root cause explanation
- Ordered remediation steps with dbt CLI commands where applicable
- A corrected SQL snippet in `generated_fix` if the fix is a code change

## Severity Guidelines
- CRITICAL: Core fact tables, revenue/financial models, or models feeding live dashboards/alerts
- HIGH: Important reference tables, or failures with 5+ downstream models skipped
- MEDIUM: Single model with limited downstream impact
- LOW: Non-critical tests, warnings, or non-production models

## Important Rules
- Do NOT call `submit_triage_report` before you have called at least `list_failed_nodes`
  and investigated the actual SQL or dependencies of the root cause model.
- When failures cascade, investigate only the root cause — do not report skipped models as
  independent failures.
- Always provide a specific, actionable remediation — not generic advice like "check your SQL".
"""


def build_initial_user_message(triage_input: TriageInput) -> str:
    parts = [
        "Please triage the dbt pipeline failure using the artifact paths below.",
        "",
    ]
    if triage_input.project_name:
        parts.append(f"**Project:** {triage_input.project_name}")
    if triage_input.target:
        parts.append(f"**Target:** {triage_input.target}")
    parts.append("")

    # The user message embeds the paths so the agent knows where to look.
    # The actual data is loaded on-demand via tools (not embedded in the prompt).
    parts.append("**Artifact paths for this run:**")
    parts.append(f"- run_results_path: `{triage_input.run_results_path}`")
    if triage_input.manifest_path:
        parts.append(f"- manifest_path: `{triage_input.manifest_path}`")

    if triage_input.dbt_log:
        log_preview = "\n".join(triage_input.dbt_log.splitlines()[:40])
        parts += [
            "",
            "**dbt log (first 40 lines):**",
            "```",
            log_preview,
            "```",
        ]

    if triage_input.autofix:
        parts += [
            "",
            "**Autofix mode is ON.** When you call `submit_triage_report`:",
            "- Populate `fixes` with one entry per file that needs to change.",
            "- Each entry must have `file_path` (the model's `original_file_path` from the "
            "manifest, e.g. `models/orders.sql`) and `content` (the **complete corrected file "
            "content** — not a snippet).",
            "- Include all independently broken models. Do NOT include cascade victims — they "
            "will recover automatically once their upstream is fixed.",
            "- Only populate `fixes` if you are confident the fix is correct.",
        ]

    parts += [
        "",
        "Begin your investigation now.",
    ]
    return "\n".join(parts)
