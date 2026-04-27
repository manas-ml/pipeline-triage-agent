TOOLS = [
    {
        "name": "list_failed_nodes",
        "description": (
            "Parse run_results.json and return all failed/errored dbt nodes with their "
            "error messages, execution time, and status. "
            "ALWAYS call this first at the start of every triage investigation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "run_results_path": {
                    "type": "string",
                    "description": "Absolute or relative path to run_results.json",
                }
            },
            "required": ["run_results_path"],
        },
    },
    {
        "name": "get_model_sql",
        "description": (
            "Retrieve the SQL source code for a specific dbt model from manifest.json. "
            "Use 'raw' to see the original Jinja template (good for spotting bad refs/macros), "
            "or 'compiled' to see the final SQL with macros resolved (what actually ran)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "manifest_path": {
                    "type": "string",
                    "description": "Path to manifest.json",
                },
                "node_id": {
                    "type": "string",
                    "description": "The dbt unique_id of the node, e.g. 'model.jaffle_shop.fct_orders'",
                },
                "sql_type": {
                    "type": "string",
                    "enum": ["raw", "compiled"],
                    "description": "Whether to return raw Jinja SQL or compiled SQL. Defaults to raw.",
                },
            },
            "required": ["manifest_path", "node_id"],
        },
    },
    {
        "name": "get_model_dependencies",
        "description": (
            "Return upstream and downstream dependencies for a dbt model from the manifest DAG. "
            "Use this to determine if a failure is a root cause or a cascade from upstream. "
            "Upstream = models this model depends on; downstream = models that depend on this model."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "manifest_path": {
                    "type": "string",
                    "description": "Path to manifest.json",
                },
                "node_id": {
                    "type": "string",
                    "description": "The dbt unique_id of the node",
                },
            },
            "required": ["manifest_path", "node_id"],
        },
    },
    {
        "name": "check_ref_resolution",
        "description": (
            "Check whether all {{ ref('X') }} calls in a model's SQL resolve to existing nodes "
            "in the manifest. Returns a list of any unresolved refs — i.e., models that are "
            "referenced but don't exist in the project. Use this when you suspect a missing or "
            "renamed model is causing the failure."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "manifest_path": {
                    "type": "string",
                    "description": "Path to manifest.json",
                },
                "node_id": {
                    "type": "string",
                    "description": "The dbt unique_id of the node to check",
                },
            },
            "required": ["manifest_path", "node_id"],
        },
    },
    {
        "name": "get_error_context",
        "description": (
            "Return the combined error message plus the first 60 lines of the model's raw SQL, "
            "giving targeted context for diagnosing the failure. Use this for SQL/compilation "
            "errors where you need to correlate the error text with the actual SQL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "manifest_path": {
                    "type": "string",
                    "description": "Path to manifest.json",
                },
                "run_results_path": {
                    "type": "string",
                    "description": "Path to run_results.json",
                },
                "node_id": {
                    "type": "string",
                    "description": "The dbt unique_id of the failed node",
                },
            },
            "required": ["manifest_path", "run_results_path", "node_id"],
        },
    },
    {
        "name": "submit_triage_report",
        "description": (
            "Submit the final structured triage report. Call this ONLY when you have fully "
            "investigated the failure using the other tools and are ready to report. "
            "Do NOT call this before you have called list_failed_nodes and inspected the "
            "relevant SQL or dependencies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "failure_type": {
                    "type": "string",
                    "description": (
                        "Classification of the failure. One of: sql_syntax_error, "
                        "relation_not_found, dependency_failure, data_quality_test, "
                        "source_freshness, permission_denied, config_error, "
                        "compilation_error, timeout, unknown"
                    ),
                },
                "severity": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low"],
                    "description": (
                        "critical=core fact/revenue models; high=important dims or many downstream; "
                        "medium=single model limited impact; low=non-critical tests or warnings"
                    ),
                },
                "root_cause": {
                    "type": "string",
                    "description": "Detailed plain-English explanation of the root cause.",
                },
                "affected_models": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of model names (not unique_ids) that are failing or skipped.",
                },
                "upstream_cause": {
                    "type": "string",
                    "description": (
                        "If this is a cascading failure, the upstream model or source that "
                        "triggered it. Null if this is the root failure."
                    ),
                },
                "remediation_steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "integer"},
                            "action": {"type": "string"},
                            "command": {"type": "string"},
                            "rationale": {"type": "string"},
                        },
                        "required": ["step", "action", "rationale"],
                    },
                    "description": "Ordered list of concrete remediation steps.",
                },
                "generated_fix": {
                    "type": "string",
                    "description": (
                        "If applicable, corrected SQL or YAML config that fixes the issue. "
                        "Include only the changed snippet, not the entire file."
                    ),
                },
                "investigation_summary": {
                    "type": "string",
                    "description": "Brief summary of what tools you called and what you found.",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Your confidence in the root cause diagnosis (0.0–1.0).",
                },
            },
            "required": [
                "failure_type",
                "severity",
                "root_cause",
                "affected_models",
                "remediation_steps",
                "investigation_summary",
                "confidence",
            ],
        },
    },
]
