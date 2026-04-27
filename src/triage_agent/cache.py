"""
Prompt caching helpers.

Builds the system message blocks with cache_control markers so Anthropic
can cache the static agent instructions between API calls.

Cache layout:
  Block 0 — Agent instructions (STATIC, ~1500 tokens) → cache_control: ephemeral
  Block 1 — (no additional blocks; manifest is accessed via tools, not embedded)

The minimum cacheable token count is 1024. The AGENT_INSTRUCTIONS string is
written to be naturally long enough to exceed this threshold.
"""
from __future__ import annotations

from .prompts import AGENT_INSTRUCTIONS


def build_system_blocks() -> list[dict]:
    """Return system message blocks with caching enabled on the static instructions."""
    return [
        {
            "type": "text",
            "text": AGENT_INSTRUCTIONS,
            "cache_control": {"type": "ephemeral"},
        }
    ]
