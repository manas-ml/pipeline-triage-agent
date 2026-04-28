"""
Core agentic loop for dbt pipeline failure triage.

Uses the Anthropic SDK tool-use pattern:
  1. Send messages with tools defined
  2. If stop_reason == "tool_use", execute all tool calls in the response
  3. Append tool results and loop
  4. When stop_reason == "end_turn" OR agent calls submit_triage_report, extract the report
"""
from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from .cache import build_system_blocks
from .models import RemediationStep, TriageInput, TriageReport
from .prompts import build_initial_user_message
from .tool_schemas import TOOLS
from .tools import TOOL_REGISTRY

MAX_TOOL_RESULT_CHARS = 12_000


class DbtTriageAgent:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
        max_iterations: int = 15,
        verbose: bool = False,
    ) -> None:
        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model
        self.max_iterations = max_iterations
        self.verbose = verbose

    def triage(self, triage_input: TriageInput) -> TriageReport:
        system_blocks = build_system_blocks()
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": build_initial_user_message(triage_input),
            }
        ]

        for iteration in range(self.max_iterations):
            if self.verbose:
                print(f"\n[Agent] Iteration {iteration + 1}/{self.max_iterations}", flush=True)

            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_blocks,
                tools=TOOLS,
                messages=messages,
            )

            # Accumulate assistant turn
            messages.append({"role": "assistant", "content": response.content})

            if self.verbose:
                print(f"[Agent] stop_reason={response.stop_reason}", flush=True)

            # Check if the agent submitted the final report via tool call
            report = self._extract_report_from_response(response)
            if report is not None:
                return report

            if response.stop_reason == "end_turn":
                # Agent finished without calling submit_triage_report — build a minimal report
                text = " ".join(
                    block.text
                    for block in response.content
                    if hasattr(block, "text")
                )
                return TriageReport(
                    failure_type="unknown",
                    severity="medium",
                    root_cause=text or "Agent completed without providing a structured report.",
                    affected_models=[],
                    remediation_steps=[],
                    investigation_summary="Agent ended without calling submit_triage_report.",
                    confidence=0.3,
                )

            if response.stop_reason != "tool_use":
                break

            # Execute all tool calls and collect results
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                if self.verbose:
                    print(f"[Tool] {tool_name}({json.dumps(tool_input)[:200]})", flush=True)

                result = self._dispatch_tool(tool_name, tool_input, triage_input)
                result_text = json.dumps(result, indent=2)

                # Truncate very large results to avoid exceeding context
                if len(result_text) > MAX_TOOL_RESULT_CHARS:
                    result_text = result_text[:MAX_TOOL_RESULT_CHARS] + "\n... [truncated]"

                if self.verbose:
                    print(f"[Tool result] {result_text[:300]}...", flush=True)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })

            # Append all tool results in a single user turn
            messages.append({"role": "user", "content": tool_results})

        # Max iterations reached — ask for a summary
        messages.append({
            "role": "user",
            "content": (
                "You have reached the maximum investigation steps. "
                "Please call submit_triage_report now with everything you have found so far."
            ),
        })
        final_response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_blocks,
            tools=TOOLS,
            tool_choice={"type": "any"},
            messages=messages,
        )
        report = self._extract_report_from_response(final_response)
        if report is not None:
            return report

        return TriageReport(
            failure_type="unknown",
            severity="medium",
            root_cause="Investigation reached maximum iterations without a conclusive diagnosis.",
            affected_models=[],
            remediation_steps=[],
            investigation_summary="Max iterations reached.",
            confidence=0.1,
        )

    def _extract_report_from_response(self, response: Any) -> TriageReport | None:
        """Return a TriageReport if the response contains a submit_triage_report tool call."""
        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_triage_report":
                return self._build_report(block.input)
        return None

    def _build_report(self, data: dict) -> TriageReport:
        steps_raw = data.get("remediation_steps", [])
        steps = []
        for i, s in enumerate(steps_raw, start=1):
            steps.append(
                RemediationStep(
                    step=s.get("step", i),
                    action=s.get("action", ""),
                    command=s.get("command"),
                    rationale=s.get("rationale", ""),
                )
            )
        return TriageReport(
            failure_type=data.get("failure_type", "unknown"),
            severity=data.get("severity", "medium"),
            root_cause=data.get("root_cause", ""),
            affected_models=data.get("affected_models", []),
            upstream_cause=data.get("upstream_cause"),
            remediation_steps=steps,
            generated_fix=data.get("generated_fix"),
            fix_file_path=data.get("fix_file_path"),
            investigation_summary=data.get("investigation_summary", ""),
            confidence=float(data.get("confidence", 0.0)),
        )

    def _dispatch_tool(
        self, tool_name: str, tool_input: dict, triage_input: TriageInput
    ) -> Any:
        handler = TOOL_REGISTRY.get(tool_name)
        if handler is None:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return handler(tool_input, triage_input)
        except Exception as exc:
            return {"error": str(exc), "tool": tool_name}
