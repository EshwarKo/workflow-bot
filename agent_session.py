"""
Agent Session Runner
====================

Reusable helper for running Claude Agent SDK sessions.
Extracts the common pattern of creating a client, sending a message,
streaming the response, and returning results.
"""

import time
import traceback
from pathlib import Path
from typing import Any


# Available models
MODELS: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-5-20250929",
    "opus": "claude-opus-4-5-20251101",
}

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompts directory."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text()


async def run_agent(
    system_prompt: str,
    task_message: str,
    cwd: Path,
    model: str,
    max_turns: int = 50,
    tools: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Run a single Claude Agent SDK session.

    Creates a fresh client, sends the task message, streams the response,
    and returns the result.

    Args:
        system_prompt: System prompt for the agent.
        task_message: The task/query to send.
        cwd: Working directory for the agent (it can Read/Write here).
        model: Full model ID string (e.g. "claude-sonnet-4-5-20250929").
        max_turns: Maximum tool-use turns before stopping.
        tools: List of allowed tools. Defaults to Read/Write/Glob/Grep.
        verbose: Whether to print streaming output.

    Returns:
        Dict with keys:
        - "text": Full response text from the agent.
        - "status": "success" or "error".
        - "error": Error message if status is "error".
        - "duration_seconds": How long the session took.
    """
    # Lazy import — SDK only needed at runtime, not for CLI --help
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        TextBlock,
        ToolUseBlock,
        UserMessage,
        ToolResultBlock,
    )

    if tools is None:
        tools = ["Read", "Write", "Glob", "Grep"]

    client = ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=model,
            system_prompt=system_prompt,
            allowed_tools=tools,
            max_turns=max_turns,
            cwd=str(cwd.resolve()),
        )
    )

    result_text = ""
    start_time = time.time()

    try:
        async with client:
            await client.query(task_message)

            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            result_text += block.text
                            if verbose:
                                print(block.text, end="", flush=True)
                        elif isinstance(block, ToolUseBlock):
                            if verbose:
                                print(f"\n  [Tool: {block.name}]", flush=True)

                elif isinstance(msg, UserMessage):
                    for block in msg.content:
                        if isinstance(block, ToolResultBlock):
                            is_error = (
                                bool(block.is_error) if block.is_error else False
                            )
                            if is_error and verbose:
                                error_str = str(block.content)[:300]
                                print(f"  [Error] {error_str}", flush=True)
                            elif verbose:
                                print("  [Done]", flush=True)

        if verbose:
            print()  # newline after streaming

        return {
            "text": result_text,
            "status": "success",
            "duration_seconds": round(time.time() - start_time, 1),
        }

    except Exception as e:
        if verbose:
            print(f"\n  Agent error: {type(e).__name__}: {e}")
        traceback.print_exc()
        return {
            "text": result_text,
            "status": "error",
            "error": str(e),
            "duration_seconds": round(time.time() - start_time, 1),
        }
