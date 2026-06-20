"""
Verifier-as-a-tool: agent.py plus one more tool. The loop is unchanged.

The agent could already verify Dafny through `bash`,
but now can do so without a permission prompt.

Run (needs `dafny` on your PATH):
    python dafny_agent.py
"""

import subprocess

from agent import DEFAULT_TOOLS, Tool, schema, main


def dafny_verify(path: str) -> str:
    try:
        p = subprocess.run(["dafny", "verify", path],
                           capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        return "[error: dafny not found on PATH]"
    status = "VERIFIED" if p.returncode == 0 else "REJECTED"
    diagnostics = (p.stdout + p.stderr).strip() or "(no output)"
    return f"{status}\n{diagnostics}"


TOOLS = DEFAULT_TOOLS + [
    Tool("dafny_verify",
         "Run the Dafny verifier on a .dfy file. Returns a status line, 'VERIFIED' "
         "or 'REJECTED', followed by the verifier's diagnostics — on REJECTED, use "
         "them to fix the code or proof.",
         schema("path"), dafny_verify),
]


if __name__ == "__main__":
    main(tools=TOOLS)
