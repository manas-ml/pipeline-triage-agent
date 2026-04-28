# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & Installation

```bash
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
```

## Commands

```bash
# Run against real dbt artifacts
dbt-triage triage \
    --run-results ./target/run_results.json \
    --manifest ./target/manifest.json \
    --verbose

# Run the built-in demo (uses examples/target/ fixtures)
dbt-triage demo --scenario sql_error    # or: missing_ref

# Output as JSON
dbt-triage triage -r ./target/run_results.json -m ./target/manifest.json --output json

# Lint
ruff check src/

# Run tests
pytest
```

## Architecture

The agent follows the Anthropic SDK **tool-use agentic loop** pattern:

1. **`cli.py`** — Click CLI; parses args, loads artifacts into Pydantic models, instantiates `DbtTriageAgent`, renders output.
2. **`agent.py`** — `DbtTriageAgent.triage()` drives the loop: send messages → if `stop_reason == tool_use`, dispatch all tool calls → append results → repeat. Terminates when `submit_triage_report` tool is called or `end_turn` is reached. Has a `max_iterations` guard that forces a final report call via `tool_choice={"type": "any"}`.
3. **`tools.py`** — Pure functions that read `manifest.json` / `run_results.json` from disk. Each maps 1-to-1 to a schema in `tool_schemas.py`. `TOOL_REGISTRY` dispatches by tool name. `submit_triage_report` is intentionally absent — it's intercepted by the agent loop, not dispatched here.
4. **`tool_schemas.py`** — Anthropic tool JSON schemas passed to `messages.create()`.
5. **`models.py`** — Pydantic models for dbt artifacts (`DbtManifest`, `DbtRunResults`) and agent I/O (`TriageInput`, `TriageReport`). `TriageReport.to_markdown()` renders the final report.
6. **`prompts.py`** — `AGENT_INSTRUCTIONS` (static system prompt) and `build_initial_user_message()`.
7. **`cache.py`** — Wraps `AGENT_INSTRUCTIONS` with `cache_control: ephemeral` to enable prompt caching across repeated runs.

## Key Design Decisions

- Tools receive raw file paths (not pre-parsed objects) so the agent can pass them through naturally from the initial user message. The CLI separately pre-parses artifacts into Pydantic models for its own validation, but `TriageInput` carries both the paths and the parsed objects.
- `MAX_TOOL_RESULT_CHARS = 12_000` in `agent.py` prevents context overflow from large manifests.
- The `submit_triage_report` tool is the agent's only way to produce a structured `TriageReport`. Text-only `end_turn` responses get wrapped in a minimal low-confidence report.
- Demo fixtures live in `examples/target/` and are referenced by absolute path relative to `cli.py`'s location.
