"""
A pure agentic loop — the core of a Claude-Code-style coding agent in one file.

Synchronous, single-provider (Anthropic), no streaming, no UI polish. The whole
agent is the `run_turn` while-loop near the bottom: send the conversation + the
tools to the LLM, run any tools it asks for, append the results, and repeat
until it stops asking for tools.

Run (AWS Bedrock — the default):
    pip install "anthropic[bedrock]"
    # AWS credentials configured (aws configure / SSO / env) with Bedrock access
    # to a Claude model in your region:
    export AWS_REGION=us-east-1
    export AGENT_MODEL=us.anthropic.claude-sonnet-4-6
    python agent.py

Run (direct Anthropic API — used when ANTHROPIC_API_KEY is set):
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    python agent.py
"""

import os
import subprocess
from dataclasses import dataclass
from typing import Callable

# Use the direct Anthropic API when ANTHROPIC_API_KEY is set; otherwise Bedrock.
USE_BEDROCK = not os.environ.get("ANTHROPIC_API_KEY")

if USE_BEDROCK:
    from anthropic import AnthropicBedrock
else:
    from anthropic import Anthropic

# A Bedrock model id / cross-region inference-profile id (default), or a plain
# Anthropic model id when using the direct API. List Bedrock profiles with:
#   aws bedrock list-inference-profiles \
#     --query 'inferenceProfileSummaries[].inferenceProfileId'
MODEL = os.environ.get(
    "AGENT_MODEL",
    "us.anthropic.claude-sonnet-4-6" if USE_BEDROCK else "claude-sonnet-4-6",
)

SYSTEM_PROMPT = """You are a small coding assistant with access to tools.
Use the tools to inspect files, edit files, and run commands. Be concise."""


# ---------------------------------------------------------------------------
# Tools. A tool is a name, a description, a JSON-Schema for its arguments, and a
# function to run. The LLM sees name/description/schema and decides when to call
# it and with what arguments; the function just does the work.
# ---------------------------------------------------------------------------

def schema(*names: str) -> dict:
    """JSON Schema for an object whose listed properties are all strings."""
    return {
        "type": "object",
        "properties": {n: {"type": "string"} for n in names},
        "required": list(names),
    }


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict                 # JSON Schema for the arguments
    run: Callable[..., str]          # called with the model-supplied kwargs
    requires_permission: bool = False

    def spec(self) -> dict:          # how Anthropic wants a tool described
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


def bash(command: str) -> str:
    p = subprocess.run(command, shell=True, capture_output=True,
                       text=True, timeout=120)
    return (p.stdout + p.stderr) or "(no output)"


def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()


def write_file(path: str, content: str) -> str:
    with open(path, "w") as f:
        f.write(content)
    return f"wrote {len(content)} bytes to {path}"


DEFAULT_TOOLS = [
    Tool("bash", "Run a shell command and return its combined stdout/stderr.",
         schema("command"), bash, requires_permission=True),
    Tool("read_file", "Read and return the contents of a file.",
         schema("path"), read_file),
    Tool("write_file", "Write text to a file, overwriting any existing contents.",
         schema("path", "content"), write_file, requires_permission=True),
]


# ---------------------------------------------------------------------------
# Permissions. Before running a tool that asks for it, prompt the user.
# "always" adds the tool to a session-wide allow-set.
# ---------------------------------------------------------------------------

def allowed(tool: Tool, args: dict, session_allow: set) -> tuple[bool, str]:
    """Return (ok, denial_message). On "no", ask why — the reason is fed back to
    the model as the tool result, so it can adjust instead of guessing."""
    if not tool.requires_permission or tool.name in session_allow:
        return True, ""
    print(f"\n  → {tool.name}({args})")
    ans = input("  allow? [y]es / [n]o / [a]lways: ").strip().lower()
    if ans == "a":
        session_allow.add(tool.name)
        return True, ""
    if ans == "y":
        return True, ""
    reason = input("  why not? (sent back to the model): ").strip()
    return False, f"[denied by user] {reason}" if reason else "[denied by user]"


# ---------------------------------------------------------------------------
# The agent loop. `messages` is the running Anthropic conversation. There are
# three message shapes:
#   user text     {"role": "user",      "content": "..."}
#   assistant     {"role": "assistant", "content": [text and/or tool_use blocks]}
#   tool results  {"role": "user",      "content": [tool_result blocks]}
# ---------------------------------------------------------------------------

def run_turn(client, tools, messages, session_allow):
    by_name = {t.name: t for t in tools}
    while True:
        reply = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[t.spec() for t in tools],
            messages=messages,
        )
        # Drop any cut-off reply: a half-written tool_use block left in
        # `messages` would break every later request.
        if reply.stop_reason == "max_tokens":
            print("[reply was cut off at the max_tokens limit and discarded]")
            return

        # Append the model's own content blocks straight back, then print text.
        messages.append({"role": "assistant", "content": reply.content})
        for block in reply.content:
            if block.type == "text":
                print(block.text)

        # No tool calls → the turn is done.
        calls = [b for b in reply.content if b.type == "tool_use"]
        if not calls:
            return

        # Run each requested tool and send the results back as a user message.
        results = []
        for call in calls:
            tool = by_name[call.name]
            ok, denial = allowed(tool, call.input, session_allow)
            if not ok:
                output, is_error = denial, True
            else:
                print(f"  · {call.name}({call.input})")
                try:
                    output, is_error = tool.run(**call.input), False
                except Exception as e:
                    output, is_error = f"[error: {e}]", True
            results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": output,
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})


def main(tools=DEFAULT_TOOLS):
    client = AnthropicBedrock() if USE_BEDROCK else Anthropic()
    messages, session_allow = [], set()
    print("pure agent — Ctrl-C to quit\n")
    while True:
        try:
            user = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        messages.append({"role": "user", "content": user})
        run_turn(client, tools, messages, session_allow)


if __name__ == "__main__":
    main()
