# Architecture

## System Overview

```mermaid
flowchart TD
    subgraph Trigger["Trigger Layer"]
        CI["CI/CD Pipeline\n(GitHub Actions, Airflow, etc.)"]
        Shell["Shell / Post-run Script\ndbt run || dbt-triage triage ..."]
    end

    subgraph CLI["CLI — cli.py"]
        Parse["Parse args\nLoad & validate artifacts"]
        Render["Render report\n(Markdown or JSON)"]
        Autofix["Apply fixes\n(--autofix)"]
    end

    subgraph Artifacts["dbt Artifacts (disk)"]
        RR["run_results.json"]
        MF["manifest.json"]
        SQL["SQL model files\nmodels/**/*.sql"]
    end

    subgraph Agent["DbtTriageAgent — agent.py"]
        Loop["Agentic Loop\n(max 15 iterations)"]
        Cache["Prompt Cache\ncache.py"]
        Prompts["System + User Prompt\nprompts.py"]
    end

    subgraph Claude["Anthropic API"]
        Model["claude-sonnet-4-6\ntool_use loop"]
    end

    subgraph Tools["Tool Layer — tools.py / tool_schemas.py"]
        T1["list_failed_nodes"]
        T2["get_error_context"]
        T3["get_model_sql"]
        T4["get_model_dependencies"]
        T5["check_ref_resolution"]
        T6["submit_triage_report\n(intercepted — not dispatched)"]
    end

    subgraph Models["Data Models — models.py"]
        TI["TriageInput"]
        TR["TriageReport\n+ fixes: FileFix[]"]
    end

    CI --> Shell
    Shell --> Parse
    Parse -->|"DbtRunResults\nDbtManifest"| TI
    TI --> Loop
    Cache --> Loop
    Prompts --> Loop
    Loop <-->|"messages + tools"| Model
    Model -->|"tool_use blocks"| Loop
    Loop -->|"dispatch"| T1 & T2 & T3 & T4 & T5
    T1 & T2 & T3 & T4 & T5 -->|"read"| RR & MF
    Loop -->|"intercept"| T6
    T6 --> TR
    TR --> Render
    TR --> Autofix
    Autofix -->|"write"| SQL
```

---

## Agentic Loop

```mermaid
sequenceDiagram
    participant CLI
    participant Agent as DbtTriageAgent
    participant API as Anthropic API
    participant Tools

    CLI->>Agent: triage(TriageInput)
    Agent->>API: messages.create(system+tools+user)

    loop Up to 15 iterations
        API-->>Agent: stop_reason=tool_use
        Agent->>Tools: dispatch each tool call
        Tools-->>Agent: JSON results
        Agent->>API: messages.create(+tool_results)
    end

    API-->>Agent: submit_triage_report tool call
    Agent-->>CLI: TriageReport

    alt --autofix and fixes present
        CLI->>CLI: write each FileFix to disk
    end
```

---

## Tool Responsibilities

```mermaid
flowchart LR
    subgraph Always["Always Called"]
        LFN["list_failed_nodes\nParse run_results.json\nReturn failed node IDs + error messages"]
    end

    subgraph Investigate["Per Failed Node"]
        GEC["get_error_context\nError message + SQL preview\n(60 lines)"]
        GMS["get_model_sql\nFull raw or compiled SQL\nfrom manifest"]
        GMD["get_model_dependencies\nUpstream + downstream\nnode lists from DAG"]
        CRR["check_ref_resolution\nScan ref() calls\nFind broken references"]
    end

    subgraph Terminal["Terminal"]
        STR["submit_triage_report\nStructured TriageReport\nincl. fixes array"]
    end

    LFN --> GEC
    GEC --> GMS
    GMS --> GMD
    GMD --> CRR
    CRR --> STR
    GEC --> STR
```

---

## Autofix — Multi-File Flow

```mermaid
flowchart TD
    Report["TriageReport\nfixes: FileFix[]"]

    Report --> Q1{{"fixes empty?"}}
    Q1 -->|Yes| Warn["Print: no fix produced"]
    Q1 -->|No| Loop

    Loop["For each FileFix\nfile_path + content"]
    Loop --> Resolve["Resolve absolute path\nmanifest/../file_path"]
    Resolve --> Q2{{"file exists?"}}
    Q2 -->|No| Skip["Print: file not found"]
    Q2 -->|Yes| Write["Overwrite file\nwith corrected SQL"]
    Write --> Next["Next fix →"]
    Next --> Loop
```

---

## Component Map

| File | Responsibility |
|------|---------------|
| `cli.py` | Entry point, artifact loading, report rendering, autofix file writes |
| `agent.py` | Agentic loop, tool dispatch, `submit_triage_report` interception |
| `tools.py` | Pure functions reading manifest/run_results from disk |
| `tool_schemas.py` | Anthropic JSON tool schemas passed to `messages.create()` |
| `models.py` | Pydantic models for dbt artifacts (`DbtManifest`, `DbtRunResults`) and agent I/O (`TriageInput`, `TriageReport`, `FileFix`) |
| `prompts.py` | Static system prompt (`AGENT_INSTRUCTIONS`) and dynamic user message builder |
| `cache.py` | Wraps system prompt with `cache_control: ephemeral` for prompt caching |
