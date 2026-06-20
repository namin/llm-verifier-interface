"""
Sketch — decomposition by proof sketch with holes (Draft-Sketch-Prove / POETRY).

The insight (DSP): a hard proof gets easy if you SKETCH its structure first —
name the helper lemmas you wish you had, prove the main goal ASSUMING them, and
only then fill each helper. The holes need each other's STATEMENTS, not each
other's proofs, so each is filled on its own.

We make 'hole' concrete with Dafny's `assume {:axiom} false;` — the analogue of
Lean's `sorry`. A lemma with that body verifies vacuously and still hands its
`ensures` to every caller. So three stages, each ending at the verifier:

    sketch    the main lemma, proved against the helpers' STATEMENTS while the
              helpers are holes (`assume {:axiom} false;`). If Dafny accepts, the
              DECOMPOSITION is sound: the goal follows from the statements alone.
    fill      each helper hole, proved on its own, with every OTHER helper still
              a hole — i.e. given only their statements, never their
              proofs. (A helper may still *call* the others; the stub's `ensures`
              is all that needs.)
    assemble  every hole filled; a trusted wrapper requires the goal and the
              auditor rules out assumptions: one fully sound proof.

Why decomposition and not token-level tree search (VerMCTS): with a strong
long-context model the live granularity is no longer the next line — the model
writes whole coherent chunks. The leverage is choosing the lemmas that cut the
problem, then proving the pieces independently.

Run (Anthropic API or Bedrock, same setup as agent.py; needs `dafny` on PATH):
    python sketch.py
"""

import re
import subprocess
import sys
from typing import Optional

from verifier_loop import generate, filter_code, verify

# The formalization is given (autoformalization is a separate concern): a list
# type with append and reverse. The decomposition is what we are after.
PREAMBLE = """\
datatype List = Nil | Cons(head: int, tail: List)

function app(xs: List, ys: List): List
{
  match xs
  case Nil => ys
  case Cons(h, t) => Cons(h, app(t, ys))
}

function rev(xs: List): List
{
  match xs
  case Nil => Nil
  case Cons(h, t) => app(rev(t), Cons(h, Nil))
}
"""

GOAL = "rev is an involution:  rev(rev(xs)) == xs  for every List xs"
GOAL_LEMMA = "lemma RevRev(xs: List)\n  ensures rev(rev(xs)) == xs"

# Trusted wrapper, appended by `assemble` and never generated. The audit rules
# out assumptions; this rules out omission: the program verifies only if RevRev
# really exists with a signature strong enough to discharge this goal. Rename or
# weaken RevRev and RequiredGoal fails to verify.
HARNESS = """
lemma RequiredGoal(xs: List)
  ensures rev(rev(xs)) == xs
{
  RevRev(xs);
}
"""

PATH = "sketch_out.dfy"
MAX_TRIES = 4


# ---------------------------------------------------------------------------
# A hole is the token `HOLE_<Name>` standing in for lemma <Name>'s body.
# `assemble` turns a sketch (the LLM's lemmas) into a full Dafny program: each
# hole becomes either a supplied proof body or `assume false;` (stub = statement
# only). PREAMBLE is prepended and the trusted HARNESS appended, so the model
# never re-derives the definitions and cannot omit the goal.
# ---------------------------------------------------------------------------

def assemble(lemmas: str, fills: dict) -> str:
    # `{:axiom}` marks the stub a deliberate hole; without it Dafny warns, and we
    # run warnings-as-errors, so a bare `assume false;` would fail the verify.
    body = re.sub(r"HOLE_(\w+)",
                  lambda m: fills.get(m.group(1), "assume {:axiom} false;"), lemmas)
    return PREAMBLE + "\n" + body + "\n" + HARNESS


def holes(lemmas: str) -> list:
    return list(dict.fromkeys(re.findall(r"HOLE_(\w+)", lemmas)))   # first-seen order


# ---------------------------------------------------------------------------
# Stage 1 — draft & sketch. The LLM writes the helper lemma STATEMENTS (bodies
# left as holes) and the main lemma's full proof skeleton that uses them. We
# accept the sketch only when it has at least one hole AND verifies with every
# hole stubbed to `assume false;` — that is the proof that the decomposition is
# sound. Verifier feedback drives the retries, exactly as in verifier_loop.py.
# ---------------------------------------------------------------------------

SKETCH_PROMPT = f"""\
These Dafny definitions are GIVEN (do not repeat them):
{PREAMBLE}
Goal: {GOAL}

Write a Dafny proof SKETCH, as a fenced ```dafny code block containing only
lemmas (not the definitions above):
  - one or more HELPER lemmas. Give each a precise signature (with `ensures`),
    and make its body exactly the single token HOLE_<Name>, where <Name> is the
    lemma's name. Example:
        lemma RevSnoc(a: List, x: int)
          ensures rev(app(a, Cons(x, Nil))) == Cons(x, rev(a))
        {{
          HOLE_RevSnoc
        }}
  - the MAIN lemma, with this exact signature, and a REAL proof body (no hole)
    that may call the helper lemmas and recurse:
        {GOAL_LEMMA}

The main proof must go through using only the helpers' `ensures` (their bodies
are holes), so choose helper statements strong enough to prove the goal.
"""


def draft_sketch() -> Optional[str]:
    feedback = ""
    for _ in range(MAX_TRIES):
        lemmas = filter_code(generate(SKETCH_PROMPT + feedback))
        if not holes(lemmas):
            feedback = "\nYour sketch had no HOLE_<Name> helper. Introduce at least one helper lemma.\n"
            continue
        ok, fb = verify(assemble(lemmas, {}), PATH)        # all helpers = assume false
        if ok:
            return lemmas
        feedback = f"\nThe sketch did not verify. Dafny said:\n{fb}\nFix the helper statements or the main proof.\n"
    return None


# ---------------------------------------------------------------------------
# Stage 2 — fill one hole, in isolation. Only this helper gets a real body; all
# the others stay holes, so its proof may rely on the others' statements but
# never their proofs. That independence is the whole point.
# ---------------------------------------------------------------------------

def fill_hole(lemmas: str, name: str) -> Optional[str]:
    feedback = ""
    for _ in range(MAX_TRIES):
        msg = generate(
            f"Given these Dafny definitions and lemma sketch:\n```dafny\n"
            f"{assemble(lemmas, {})}\n```\n"
            f"Provide ONLY the proof body (Dafny statements, no braces) that should "
            f"replace HOLE_{name} in lemma {name}. You may call the other lemmas by "
            f"name; assume they hold.{feedback}")
        body = filter_code(msg).strip()
        ok, fb = verify(assemble(lemmas, {name: body}), PATH)   # others still holes
        if ok:
            return body
        feedback = f"\nThat body did not verify. Dafny said:\n{fb}\n"
    return None


# ---------------------------------------------------------------------------
# The audit. `dafny verify` passes the {:axiom} escapes, so a green verdict can't
# back "nothing assumed" — a fill could smuggle in `assume {:axiom} false;` and
# still verify. Dafny's soundness auditor flags them (assumes, {:axiom}s,
# bodyless definitions, externs); a sound assembly has 0 findings.
# ---------------------------------------------------------------------------

def audit(path: str) -> tuple[bool, str]:
    p = subprocess.run(["dafny", "audit", path],
                       capture_output=True, text=True, timeout=120)
    out = (p.stdout + p.stderr).strip()
    # Audit findings still produce exit code 0, so check the finding count too.
    m = re.search(r"completed with (\d+) finding", out)
    return p.returncode == 0 and m is not None and m.group(1) == "0", out


# ---------------------------------------------------------------------------

def main():
    print(f"GOAL: {GOAL}\n\n--- stage 1: draft & sketch ---")
    lemmas = draft_sketch()
    if lemmas is None:
        print("could not produce a verifying sketch"); return 1
    hs = holes(lemmas)
    print(f"sketch verifies; the decomposition is sound. holes: {hs}\n")
    print(assemble(lemmas, {}))

    print("\n--- stage 2: fill each hole independently ---")
    fills = {}
    for name in hs:
        body = fill_hole(lemmas, name)
        if body is None:
            print(f"could not fill {name}"); return 1
        fills[name] = body
        print(f"  {name}: filled and verified (others still holes)")

    print("\n--- stage 3: assemble, verify & audit (nothing assumed) ---")
    program = assemble(lemmas, fills)
    ok, fb = verify(program, PATH)          # proves the goal, modulo any assumptions
    if not ok:
        print(f"assembly did not verify: {fb}")
        return 1
    clean, report = audit(PATH)             # confirms there are NO assumptions
    if not clean:                           # verified, but vacuously — the lesson
        print("assembly verifies but the auditor found trust escapes "
              "(a fill smuggled in an assumption):\n" + report)
        return 1
    print("\n" + program +
          "\nFULLY VERIFIED and AUDITED — 0 findings, no assumptions remain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
