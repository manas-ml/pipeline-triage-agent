# dbt Pipeline Failure Triage Agent

An AI-powered agent that automatically triages dbt pipeline failures using the [Anthropic Claude SDK](https://docs.anthropic.com/en/api/getting-started).

When a dbt run fails, the agent reads `run_results.json` and `manifest.json`, iteratively calls tools to inspect SQL, trace dependencies, and identify broken refs, then produces a structured Markdown remediation report.

## Quick Start

```bash
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...

# Run against real dbt artifacts
dbt-triage triage \
    --run-results ./target/run_results.json \
    --manifest ./target/manifest.json \
    --verbose

# Run the built-in demo
dbt-triage demo --scenario sql_error
```

## Testing Against a Local dbt Project

After any `dbt run`, `dbt test`, or `dbt build`, dbt writes artifacts to `target/`. Point the agent at those files:

```bash
cd your-dbt-project

# 1. Run dbt (failures are required — the agent exits early if everything passed)
dbt run

# 2. Triage whatever failed
dbt-triage triage \
    --run-results ./target/run_results.json \
    --manifest ./target/manifest.json \
    --verbose
```

To intentionally generate a failure for testing, break a model or run a single known-bad model:

```bash
dbt run --select my_broken_model
dbt-triage triage \
    --run-results ./target/run_results.json \
    --manifest ./target/manifest.json
```

`--manifest` is optional but strongly recommended — without it the agent cannot inspect SQL or trace dependencies.

## How It Works

The agent uses a **tool-use agentic loop** with the Anthropic Python SDK:

1. Claude receives the artifact paths and a system prompt describing the triage protocol
2. Claude calls tools (`list_failed_nodes`, `get_model_sql`, `get_model_dependencies`, `check_ref_resolution`, `get_error_context`) to investigate
3. After gathering evidence, Claude calls `submit_triage_report` with a structured diagnosis
4. The loop terminates and the CLI renders the report as Markdown or JSON

**Prompt caching** is used on the system prompt to reduce latency and cost across repeated runs.

## Failure Types Handled

| Type | Example |
|------|---------|
| `sql_syntax_error` / `relation_not_found` | Column `order_amount` doesn't exist — typo vs actual column name `amount` |
| `compilation_error` / `dependency_failure` | `{{ ref('stg_payments') }}` but model was renamed to `stg_payment_methods` |

## Project Structure

```
src/triage_agent/
├── agent.py          # Core agentic loop (Anthropic SDK tool-use)
├── tools.py          # Tool implementations (read dbt artifacts from disk)
├── tool_schemas.py   # Anthropic tool JSON schemas
├── models.py         # Pydantic models for manifest + run_results
├── prompts.py        # System prompt and user message builder
├── cache.py          # Prompt caching helpers
└── cli.py            # Click CLI entry point

examples/
├── target/
│   ├── manifest.json      # Sample dbt manifest with 5 models
│   └── run_results.json   # Two failures: SQL column error + missing ref
└── models/                # Example SQL model files
```
