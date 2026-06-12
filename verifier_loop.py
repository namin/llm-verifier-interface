"""
Verifier-in-the-loop: the verifier's verdict, not the model, ends the loop.

In agent.py the loop ends when the model stops asking for tools — the model
decides when it is done. Here the model has no say: `step` ends only when
Dafny accepts or the budget runs out. The pieces are named so the file reads
as the architecture:

    generate     the heuristic — prompt in, text out; the only LLM call
    filter_code  extract the candidate program from the reply
    verify       the judge — Dafny's verdict and its feedback
    step         propose, check, recurse on the feedback

The model is stateless: each step rebuilds the prompt from the last failed
candidate and the verifier's feedback. Replace "recurse once" with "branch"
and `step` becomes tree search.

Run (AWS Bedrock by default, direct Anthropic API when ANTHROPIC_API_KEY is
set — same setup as agent.py; also needs `dafny` on your PATH):
    python verifier_loop.py "A factorial function, and a lemma proving it is always positive."
"""

import os
import re
import subprocess
import sys
from typing import Optional

USE_BEDROCK = not os.environ.get("ANTHROPIC_API_KEY")

if USE_BEDROCK:
    from anthropic import AnthropicBedrock
else:
    from anthropic import Anthropic

MODEL = os.environ.get(
    "AGENT_MODEL",
    "us.anthropic.claude-sonnet-4-6" if USE_BEDROCK else "claude-sonnet-4-6",
)


def generate(prompt: str) -> str:
    client = AnthropicBedrock() if USE_BEDROCK else Anthropic()
    reply = client.messages.create(model=MODEL, max_tokens=4096,
                                   messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in reply.content if b.type == "text")


def filter_code(text: str) -> str:
    m = re.search(r"```(?:[Dd]afny)?\n(.*?)```", text, re.S)
    return m.group(1) if m else text


def verify(code: str, path: str = "out.dfy") -> tuple[bool, str]:
    with open(path, "w") as f:
        f.write(code)
    p = subprocess.run(["dafny", "verify", path],
                       capture_output=True, text=True, timeout=120)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def step(instructions: str, code: Optional[str] = None,
         feedback: Optional[str] = None, steps: int = 0,
         max_steps: int = 3) -> Optional[str]:
    prompt = f"""
Generate Dafny code for the following instructions:
{instructions}
"""
    if code and feedback:
        prompt += f"""
A previously unsuccessful code is:
```
{code}
```
The output of the verification was:
{feedback}
"""
    prompt += """Enter the entire code for the instructions in a block of code. Do not include any other text."""

    code = filter_code(generate(prompt))
    ok, feedback = verify(code)
    if ok:
        print(f"Success! {feedback}")
        return code  # the only success exit: Dafny said yes
    print(f"Failed! {feedback}")
    if steps < max_steps:
        return step(instructions, code, feedback, steps + 1, max_steps)
    return None


if __name__ == "__main__":
    instructions = sys.argv[1] if len(sys.argv) > 1 else """
    A factorial function, and a lemma proving it is always positive.
    """
    code = step(instructions)
    print(code if code else "budget exhausted: NOT verified")
    sys.exit(0 if code else 1)  # the exit status is the verdict
