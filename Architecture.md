# Architecture

## System Overview

```
  CI / Shell
      │
      ▼
 ┌─────────────────────────────────────────────────────┐
 │                      CLI (cli.py)                   │
 │  load run_results.json + manifest.json → TriageInput│
 └───────────────────┬─────────────────────────────────┘
                     │
                     ▼
 ┌─────────────────────────────────────────────────────┐
 │              DbtTriageAgent (agent.py)               │
 │                                                     │
 │  ┌─────────────┐        ┌──────────────────────┐   │
 │  │  Prompts +  │──────▶│   Anthropic API       │   │
 │  │  Cache      │◀──────│   claude-sonnet-4-6   │   │
 │  └─────────────┘        └──────────┬───────────┘   │
 │                                    │ tool_use       │
 │                          ┌─────────▼─────────┐     │
 │                          │    Tool Dispatch   │     │
 │                          └─────────┬─────────┘     │
 └────────────────────────────────────│───────────────┘
                                      │
                     ┌────────────────┼────────────────┐
                     ▼                ▼                 ▼
             run_results.json    manifest.json    manifest.json
```

---

## Agentic Loop

```
  Agent                          Anthropic API
    │                                 │
    │── messages + tools ───────────▶│
    │                                 │
    │◀─────────────── tool_use ───────│
    │                                 │
    │  dispatch tool → read artifact  │
    │                                 │
    │── tool_results ───────────────▶│
    │                                 │
    │    (repeat up to 15 times)      │
    │                                 │
    │◀────── submit_triage_report ────│
    │                                 │
  TriageReport
```

---

## Tools

```
  list_failed_nodes        → parse run_results.json, return failed node IDs
  get_error_context        → error message + SQL preview for a node
  get_model_sql            → raw or compiled SQL from manifest
  get_model_dependencies   → upstream + downstream nodes from DAG
  check_ref_resolution     → find broken ref() calls in SQL
  submit_triage_report     → terminal: produce structured TriageReport
```

---

## Autofix (--autofix)

```
  TriageReport.fixes[]
        │
        ├── FileFix { file_path: "models/orders.sql",   content: "..." }
        ├── FileFix { file_path: "models/payments.sql",  content: "..." }
        └── ...
              │
              ▼
        resolve: manifest/../file_path → absolute path
              │
              ▼
        overwrite SQL file on disk
```

---

## Component Map

```
cli.py            Entry point, artifact loading, report rendering, autofix writes
agent.py          Agentic loop, tool dispatch, submit_triage_report interception
tools.py          Pure functions reading manifest / run_results from disk
tool_schemas.py   Anthropic JSON tool schemas
models.py         Pydantic models: DbtManifest, DbtRunResults, TriageReport, FileFix
prompts.py        System prompt (AGENT_INSTRUCTIONS) + user message builder
cache.py          Wraps system prompt with cache_control: ephemeral
```
