"""
CEGIS — Counterexample-Guided Inductive Synthesis — with an LLM as the synthesizer.

What makes a loop CEGIS (and not just retry-until-it-passes) is two things:

  1. Two asymmetric roles.
       synthesize  the INDUCTIVE half: produce a candidate that is correct on a
                   finite set of concrete example inputs. No soundness duty — it
                   may generalize wrongly. Classically an SMT/enumerative solver;
                   here an LLM (the heuristic).
       verify      the DEDUCTIVE half: check the candidate against the FULL spec,
                   for ALL inputs. Either it certifies (no input violates the
                   spec) or it returns ONE concrete input where the candidate is
                   wrong. Here Z3 (the soundness guarantee).

  2. Counterexample ACCUMULATION. Every failure adds a concrete input to a set
     that only grows. The synthesizer is re-run against the whole accumulated
     set each round. The set of counterexamples is the entire memory of the loop.

Two reference points, one outside this repo and one inside it:

  * minisynth (Adrian Sampson's solver-only synthesizer,
    https://www.cs.cornell.edu/~asampson/blog/minisynth.html) does a one-shot
    solve, handing Z3 the quantifier directly:
        find holes such that  FORALL x. sketch(holes, x) == spec(x)
    one query, no loop. CEGIS instead *removes* the FORALL: it asks the
    synthesizer only "be right on these finitely many x" (quantifier-free), and
    pushes the FORALL into the verifier as a satisfiability check. It trades one
    hard EXISTS-FORALL query for a sequence of easy quantifier-free ones.

  * verifier_loop.py has the loop shape (propose, check, repeat) but keeps only
    the LAST failure in the prompt. CEGIS keeps them ALL. That accumulation is
    the difference. A classical constrained synthesizer cannot repeat an earlier
    mistake — the examples are hard constraints on it. Here the synthesizer is an
    LLM, so accumulation gives it persistent feedback (every pinned input stays in
    front of it) but does not guarantee convergence: the model may ignore them.

Run (Anthropic API or Bedrock, same setup as agent.py; needs z3-solver):
    pip install z3-solver anthropic
    python cegis.py                 # default: synthesize absolute value
    python cegis.py relu
"""

import ast
import operator
import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, Optional

import z3

USE_BEDROCK = not os.environ.get("ANTHROPIC_API_KEY")

if USE_BEDROCK:
    from anthropic import AnthropicBedrock
else:
    from anthropic import Anthropic

MODEL = os.environ.get(
    "AGENT_MODEL",
    "us.anthropic.claude-sonnet-4-6" if USE_BEDROCK else "claude-sonnet-4-6",
)


# ---------------------------------------------------------------------------
# The specification. `phi(x, y)` is a Z3 predicate meaning "y is a correct
# output for input x". It is the FULL spec — quantified implicitly over all x —
# and it is the only thing the verifier trusts. The English `description` is for
# the LLM synthesizer, which cannot read Z3.
# ---------------------------------------------------------------------------

@dataclass
class Spec:
    name: str
    description: str
    phi: Callable[[z3.ExprRef, z3.ExprRef], z3.BoolRef]


SPECS = {
    "abs": Spec(
        "abs", "the absolute value of x",
        lambda x, y: z3.And(y >= x, y >= -x, z3.Or(y == x, y == -x))),
    "relu": Spec(
        "relu", "the maximum of x and 0",
        lambda x, y: z3.And(y >= 0, y >= x, z3.Or(y == 0, y == x))),
    "double": Spec(
        "double", "twice x",
        lambda x, y: y == x + x),
}


# ---------------------------------------------------------------------------
# A candidate is an expression in `x` from a tiny grammar: int literals, x,
# + - *, and If(cond, a, b). We parse it and walk the tree, building the Z3 term
# structurally — overloaded operators still do the work (`x*2` becomes x*2). The
# interpreter below IS the candidate language; no eval, so no sandbox to get wrong.
# ---------------------------------------------------------------------------

BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul}
CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne,
       ast.Lt: operator.lt, ast.LtE: operator.le,
       ast.Gt: operator.gt, ast.GtE: operator.ge}


def build(expr: str, x: z3.ExprRef) -> z3.ExprRef:
    # eval would do it, but expr is LLM-generated and {"__builtins__": {}} is no
    # sandbox (attribute-walking escapes it):
    #     term = eval(expr, {"__builtins__": {}}, {"x": x, "If": z3.If})
    #     return z3.IntVal(term) if isinstance(term, int) else term
    # So we walk the tree and build the Z3 term structurally instead.
    def go(node):
        if isinstance(node, ast.Expression):
            return go(node.body)
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return z3.IntVal(node.value)
        if isinstance(node, ast.Name) and node.id == "x":
            return x
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return go(node.operand) if isinstance(node.op, ast.UAdd) else -go(node.operand)
        if isinstance(node, ast.BinOp) and type(node.op) in BIN:
            return BIN[type(node.op)](go(node.left), go(node.right))
        if (isinstance(node, ast.Compare) and len(node.ops) == 1
                and type(node.ops[0]) in CMP):
            return CMP[type(node.ops[0])](go(node.left), go(node.comparators[0]))
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "If" and len(node.args) == 3
                and not node.keywords):
            return z3.If(*(go(arg) for arg in node.args))
        raise ValueError(f"disallowed syntax: {ast.dump(node, include_attributes=False)}")

    term = go(ast.parse(expr, mode="eval"))
    if not z3.is_int(term):
        raise ValueError("candidate must be integer-valued")
    return term


# ---------------------------------------------------------------------------
# The verifier (deductive). Ask Z3 for ANY input that violates the spec:
#     SAT      exists x. NOT phi(x, candidate(x))  ->  a concrete counterexample
#     UNSAT                                        ->  correct for ALL inputs
#     UNKNOWN  Z3 could not decide  ->  NOT a certificate (only UNSAT certifies)
# When it fails, we also ask the spec for a witness of a correct output at that
# input, purely to give the synthesizer a more useful hint.
# ---------------------------------------------------------------------------

def verify(spec: Spec, term: z3.ExprRef, x: z3.ExprRef):
    s = z3.Solver()
    s.add(z3.Not(spec.phi(x, term)))
    r = s.check()
    if r == z3.unsat:
        return None                       # certified: no input breaks the spec
    if r == z3.unknown:                   # Z3 gave up — never a certificate
        return ("unknown", s.reason_unknown())
    m = s.model()
    # Z3 may omit x from the model when every value violates the spec; complete it.
    x0 = m.eval(x, model_completion=True).as_long()
    wrong = m.eval(term, model_completion=True).as_long()
    return x0, wrong, witness(spec, x0)


def witness(spec: Spec, x0: int) -> Optional[int]:
    """A correct output at x0, if one exists — derived from the spec itself."""
    y = z3.Int("y")
    s = z3.Solver()
    s.add(spec.phi(z3.IntVal(x0), y))
    return s.model()[y].as_long() if s.check() == z3.sat else None


# ---------------------------------------------------------------------------
# The synthesizer (inductive) — an LLM. It sees the English spec, the running
# list of counterexamples, and its last attempt, and proposes a new expression.
# Unlike a solver-synthesizer it is NOT guaranteed to satisfy the accumulated
# examples; passing the whole set every round is what pushes it to.
# ---------------------------------------------------------------------------

GRAMMAR = ("a single Python expression in the integer variable x, using only "
           "integer literals, x, +, -, *, parentheses, and If(cond, a, b) where "
           "cond uses == != < <= > >= . No other functions, no division.")


def synthesize(spec: Spec, examples: list, last: Optional[str],
               error: Optional[str]) -> str:
    prompt = f"You are the synthesizer in a CEGIS loop. Propose {GRAMMAR}\n\n"
    prompt += f"It must compute {spec.description}, for every integer x.\n"
    if last:
        prompt += f"\nYour previous attempt was: {last}\n"
    if error:
        prompt += f"It could not be parsed as a Z3 term: {error}\n"
    if examples:
        prompt += "\nIt was WRONG on these inputs (these must all be fixed):\n"
        for x0, wrong, correct in examples:
            prompt += (f"  x = {x0}: your expression gives {wrong}, "
                       f"but a correct output is {correct}\n")
    prompt += "\nReturn ONLY the expression, nothing else."

    client = AnthropicBedrock() if USE_BEDROCK else Anthropic()
    reply = client.messages.create(model=MODEL, max_tokens=1024,
                                   messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in reply.content if b.type == "text").strip()
    return extract(text)


def extract(text: str) -> str:
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.S)
    expr = (m.group(1) if m else text).strip()
    expr = expr.splitlines()[0].strip().rstrip(";")   # first line, no trailing ;
    if "lambda" in expr:                              # tolerate "lambda x: ..."
        expr = expr.split(":", 1)[1].strip()
    return expr


# ---------------------------------------------------------------------------
# The CEGIS loop. `examples` is the accumulated counterexample set — the whole
# state. synthesize (induce from examples) -> verify (deduce over all inputs) ->
# on failure, accumulate the new counterexample and repeat. The verifier, not
# the model, ends the loop: it stops only on UNSAT (proven correct everywhere).
# ---------------------------------------------------------------------------

def cegis(spec: Spec, synth: Callable = synthesize,
          max_rounds: int = 10) -> Optional[str]:
    x = z3.Int("x")
    examples, last, error = [], None, None
    for r in range(1, max_rounds + 1):
        expr = synth(spec, examples, last, error)
        last, error = expr, None
        print(f"round {r}: candidate = {expr}")
        try:
            term = build(expr, x)
        except Exception as e:                        # not even a valid term
            error = str(e)
            print(f"         unparsable: {e}")
            continue
        cex = verify(spec, term, x)
        if cex is None:
            print(f"         VERIFIED for all integers: {spec.name}(x) = {expr}")
            return expr
        if cex[0] == "unknown":                       # undecided — fail closed
            print(f"         Z3 returned unknown ({cex[1]}); NOT certified")
            return None
        x0, wrong, correct = cex
        print(f"         counterexample x={x0}: got {wrong}, want {correct}")
        if not any(e[0] == x0 for e in examples):     # accumulate (dedup by input)
            examples.append((x0, wrong, correct))
    print("         budget exhausted: NOT verified")
    return None


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "abs"
    result = cegis(SPECS[name])
    sys.exit(0 if result else 1)             # exit status is the verifier's verdict
