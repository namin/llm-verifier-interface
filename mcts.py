"""
MCTS — Monte Carlo Tree Search, with the verifier in place of the rollout.

This is the SEARCH pillar in miniature: how to spend a fixed budget of verifier
calls over a branching space of partial solutions, and beat the obvious
alternatives. No LLM here — the point is the algorithm; the LLM's only job in the
real thing is the policy (which child to try), and we hold that fixed so the
lesson is clean.

Two ideas, both fundamental and both still true after long context made VerMCTS's
*token-level* granularity dated:

  1. The verifier replaces the Monte Carlo rollout. Classic MCTS estimates a
     node's value by random simulation to the end. In a verified setting you have
     a SOUND oracle, so use it: prune branches it proves dead, and optimistically
     value the ones it cannot rule out. `evaluate()` below is the verifier,
     not a dice roll. This is AlphaZero's move (Silver et al., 2017): drop the
     rollout, read an evaluator at the leaf. AlphaZero's evaluator is a learned
     value network; here it is a sound verifier, and the LLM would play the role
     of AlphaZero's policy head (which child to try) — uniform in this toy.

  2. UCT is budget allocation. Selection spends the next verifier call where it
     is most worth it — exploit high-value subtrees, explore under-visited ones.

The controlled experiment at the bottom makes the payoff visible: MCTS vs
best-of-N with the SAME policy, the SAME verifier, and the SAME call budget. The
only difference is structure — MCTS builds a tree (shared prefixes, UCT) while
best-of-N samples independent attempts from the root. Sweeping the budget in two
regimes shows the catch: when the verifier is informative (a narrow corridor it
prunes hard) MCTS pays a small startup cost then dominates on structure alone;
when it is uninformative (lots of slack, little it can prune) the tree is dead
weight and best-of-N keeps pace. Structure pays off exactly to the extent the
partial verifier is informative.

Granularity is the design knob, not part of the algorithm. Here a step is a
toy arithmetic op; swap in: tactics (AlphaProof), subgoals (DeepSeek-Prover),
helper lemmas (sketch.py), or — for a weak model — lines (the original VerMCTS).
The select/expand/evaluate/backprop skeleton is identical.

Run:
    python mcts.py
"""

import math
import random
from typing import Optional

# ---------------------------------------------------------------------------
# The toy domain. Build TARGET from 1 by a sequence of ops. A state is
# (value, ops). The "verifier" is one SOUND check, classify(state):
#   solved  value == TARGET
#   dead    value > TARGET (ops never decrease, so overshoot is unreachable),
#           OR the most you could still reach in the steps left is < TARGET
#   open    neither — not ruled out, not yet done
# `dead` is genuine partial verification: it rejects prefixes that provably
# cannot be completed, with no rollout. One call per state is the budgeted unit.
# The policy (which op next) is uniform — this is exactly where an LLM would go.
# ---------------------------------------------------------------------------

# TARGET sits near the most you can reach in MAX_DEPTH steps, so the live corridor
# is narrow: most prefixes either overshoot or can no longer catch up, and
# classify prunes them as `dead`. That is the regime where partial
# verification is informative and search pays off — slack makes every prefix look
# fine and there is nothing for the verifier (or the search) to grip.
OPS = [("+1", lambda v: v + 1), ("*2", lambda v: v * 2), ("*3", lambda v: v * 3)]
START = 1
TARGET = 243        # = 3^5; reachable in 5–6 steps, but only by near-maximal growth
MAX_DEPTH = 6


def step(state, i):
    name, f = OPS[i]
    return (f(state[0]), state[1] + (name,))


def max_reach(v, steps):
    for _ in range(steps):                       # ops are monotone: greedy = exact max
        v = max(f(v) for _, f in OPS)
    return v


class Verifier:
    """One sound check, classify(), against a hard budget of calls. The search
    must check exhausted() before each call; the assert catches any overspend.
    target and max_depth ARE the obligation — and how tight the live corridor is,
    the knob the ablation at the bottom turns."""
    def __init__(self, budget: int, target: int = TARGET, max_depth: int = MAX_DEPTH):
        self.budget = budget
        self.target = target
        self.max_depth = max_depth
        self.calls = 0

    def exhausted(self) -> bool:
        return self.calls >= self.budget

    def classify(self, state) -> str:
        assert not self.exhausted(), "verifier called past its budget"
        self.calls += 1
        v, ops = state
        if v == self.target:
            return "solved"
        if v > self.target or max_reach(v, self.max_depth - len(ops)) < self.target:
            return "dead"
        return "open"


def render(state) -> str:
    s = str(START)
    for op in state[1]:
        s = f"({s}{op})"
    return s


# ---------------------------------------------------------------------------
# MCTS. select -> expand -> evaluate (the verifier) -> backpropagate, under UCT.
# ---------------------------------------------------------------------------

class Node:
    def __init__(self, state, parent=None):
        self.state = state
        self.parent = parent
        self.children = []
        self.untried = None          # set lazily to the shuffled op indices
        self.N = 0
        self.W = 0.0
        self.solved = False
        self.closed = False          # subtree fully explored — skipped in SELECT

    def full(self) -> bool:
        return self.untried is not None and not self.untried


def evaluate(node, verifier) -> float:
    """The rollout, replaced by one verifier call: dead -> 0, solved/open -> 1.
    `dead` already covers out-of-depth (no steps left), so nothing extra here."""
    kind = verifier.classify(node.state)
    if kind == "solved":
        node.solved = node.closed = True
        return 1.0
    if kind == "dead":
        node.closed = True                                 # pruned
        return 0.0
    return 1.0                                             # open: optimistic upper bound


def backprop(node, value) -> None:
    while node:
        node.N += 1
        node.W += value
        # Closed = solved/dead leaf, or fully expanded with every child closed.
        # SELECT skips closed nodes, so this empties the frontier and lets the
        # search stop once nothing expandable remains.
        if not node.closed and node.full() and node.children \
                and all(ch.closed for ch in node.children):
            node.closed = True
        node = node.parent


# UCT — the selection rule. The full PUCT (VerMCTS, and on the slides) is
#
#     score(s,a) = mean(s,a) + c_UCT * p(s,a) * sqrt( log N(s) / (1 + N(s,a)) )
#
# where mean(s,a) (the slide's X-bar) averages the verifier feedback and the
# policy prior p(s,a) drives progressive widening: which child to add, and
# whether to widen at all. This toy has a uniform policy and a fixed branching of
# three, so p(s,a) is constant and there is nothing to widen — it would be dead
# weight here. Dropping it leaves plain UCT,
#
#     score = W/N + c * sqrt( log N(parent) / N ),
#
# with W/N = mean(s,a). The `1 + N(s,a)` smoothing is unneeded too: every child is
# evaluated and backpropagated the moment it is created, so N >= 1 before
# selection ever scores it (no zero to guard against).
def uct(node, c) -> float:
    return node.W / node.N + c * math.sqrt(math.log(node.parent.N) / node.N)


def mcts(verifier, rng, c=1.4) -> Optional[tuple]:
    root = Node((START, ()))
    backprop(root, evaluate(root, verifier))                          # one call
    # Stop on budget, or when the root closes (whole tree explored). A dead root
    # closes on its first evaluation, so the loop never runs.
    while not verifier.exhausted() and not root.closed:
        node = root
        while node.full() and not node.closed:                       # SELECT
            node = max((ch for ch in node.children if not ch.closed),
                       key=lambda n: uct(n, c))
        if node.untried is None:                                     # EXPAND
            node.untried = list(range(len(OPS)))
            rng.shuffle(node.untried)
        child = Node(step(node.state, node.untried.pop()), node)
        node.children.append(child)
        value = evaluate(child, verifier)                            # EVALUATE (one call)
        backprop(child, value)                                       # BACKPROP
        if child.solved:
            return child.state
    return None


# ---------------------------------------------------------------------------
# The baseline: best-of-N. SAME policy (uniform), SAME verifier, SAME budget —
# but no tree. Each attempt is independent from the root, abandoning a line the
# verifier proves dead. It cannot reuse a good prefix or shift budget toward it.
# ---------------------------------------------------------------------------

def best_of_n(verifier, rng) -> Optional[tuple]:
    while not verifier.exhausted():
        state = (START, ())
        while not verifier.exhausted():                # gate every call: no overshoot
            kind = verifier.classify(state)
            if kind == "solved":
                return state
            if kind == "dead":
                break                                  # dead line, start a new attempt
            state = step(state, rng.randrange(len(OPS)))
    return None


# ---------------------------------------------------------------------------
# The ablation. One budget point can look cherry-picked, so sweep the budget and
# report solve-rate — the success-probability curve — in two regimes that differ
# ONLY in how informative the partial verifier is. Same policy, same verifier,
# same budgets throughout; only MCTS's tree and the regime change.
#
#   informative    (TARGET, MAX_DEPTH): target near the most reachable, the
#                  corridor is narrow, classify prunes most prefixes as `dead`.
#                  MCTS pays a small startup cost, then dominates: pruning frees
#                  budget and shared prefixes are reused.
#   uninformative  (LOOSE_*): lots of depth slack, almost every prefix stays
#                  `open`, classify rarely prunes. With no signal to exploit the
#                  tree is dead weight — best-of-N's independent dives keep pace
#                  or lead until the budget is large enough for both to saturate.
#
# The lesson is not "MCTS wins" but "structure pays off exactly to the extent the
# partial verifier is informative."
# ---------------------------------------------------------------------------

LOOSE_TARGET, LOOSE_DEPTH = 60, 14


def solved(search, budget, seeds, target, max_depth) -> int:
    return sum(bool(search(Verifier(budget, target, max_depth), random.Random(s)))
               for s in range(seeds))


def sweep(label, target, max_depth, budgets, seeds=40):
    print(f"{label}\n  {'budget':>6}  {'MCTS':>7}  {'best-of-N':>9}")
    for b in budgets:
        m = solved(mcts, b, seeds, target, max_depth)
        n = solved(best_of_n, b, seeds, target, max_depth)
        print(f"  {b:>6}  {f'{m}/{seeds}':>7}  {f'{n}/{seeds}':>9}")
    print()


def compare(budgets=(20, 40, 80, 160, 320), seeds=40):
    sweep(f"informative — build {TARGET} from {START} in <={MAX_DEPTH} steps "
          f"(narrow corridor; classify prunes hard)",
          TARGET, MAX_DEPTH, budgets, seeds)
    sweep(f"uninformative — build {LOOSE_TARGET} from {START} in <={LOOSE_DEPTH} "
          f"steps (lots of slack; classify rarely prunes)",
          LOOSE_TARGET, LOOSE_DEPTH, budgets, seeds)


if __name__ == "__main__":
    sol = mcts(Verifier(300), random.Random(0))
    print("one MCTS solution:", f"{render(sol)} = {sol[0]}" if sol else None, "\n")
    compare()
