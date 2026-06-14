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
     value the ones it proves still-feasible. `evaluate()` below is the verifier,
     not a dice roll. This is AlphaZero's move (Silver et al., 2017): drop the
     rollout, read an evaluator at the leaf. AlphaZero's evaluator is a learned
     value network; here it is a sound verifier, and the LLM would play the role
     of AlphaZero's policy head (which child to try) — uniform in this toy.

  2. UCT is budget allocation. Selection spends the next verifier call where it
     is most worth it — exploit high-value subtrees, explore under-visited ones.

The controlled experiment at the bottom makes the payoff visible: MCTS vs
best-of-N with the SAME policy, the SAME verifier, and the SAME call budget. The
only difference is structure — MCTS builds a tree (shared prefixes, UCT) while
best-of-N samples independent attempts from the root. MCTS wins, and it wins
purely on structure.

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
# (value, ops). The "verifier" is two SOUND checks on a (partial) state:
#   solved  value == TARGET
#   alive   value <= TARGET   (ops never decrease, so overshoot is unreachable)
#            AND the most you could still reach in the steps left is >= TARGET
# `alive` is genuine partial verification: it rejects prefixes that provably
# cannot be completed, with no rollout. The policy (which op next) is uniform —
# this is exactly where an LLM would go.
# ---------------------------------------------------------------------------

# TARGET sits near the most you can reach in MAX_DEPTH steps, so the live corridor
# is narrow: most prefixes either overshoot or can no longer catch up, and the
# verifier's `alive` check prunes them. That is the regime where partial
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
    """Wraps the sound checks and counts calls — calls are the budgeted resource."""
    def __init__(self):
        self.calls = 0

    def solved(self, state) -> bool:
        self.calls += 1
        return state[0] == TARGET

    def alive(self, state) -> bool:
        self.calls += 1
        v, ops = state
        return v <= TARGET and max_reach(v, MAX_DEPTH - len(ops)) >= TARGET


def render(state) -> str:
    s = str(START)
    for op in state[1]:
        s = f"({s}{op})"
    return s


# ---------------------------------------------------------------------------
# MCTS. select -> expand -> evaluate (the verifier) -> backpropagate, under UCT.
# ---------------------------------------------------------------------------

class Node:
    __slots__ = ("state", "parent", "children", "untried", "N", "W",
                 "value", "terminal", "solved")

    def __init__(self, state, parent=None):
        self.state = state
        self.parent = parent
        self.children = []
        self.untried = None          # set lazily to the shuffled op indices
        self.N = 0
        self.W = 0.0
        self.value = 0.0
        self.terminal = False
        self.solved = False

    def full(self) -> bool:
        return self.untried is not None and not self.untried


def evaluate(node, verifier) -> None:
    """The rollout, replaced by the verifier: dead -> 0, solved/alive -> 1."""
    if not verifier.alive(node.state):
        node.value, node.terminal = 0.0, True              # pruned: provably dead
    elif verifier.solved(node.state):
        node.value, node.terminal, node.solved = 1.0, True, True
    elif len(node.state[1]) >= MAX_DEPTH:
        node.value, node.terminal = 0.0, True              # out of depth, unsolved
    else:
        node.value = 1.0                                   # alive: optimistic upper bound


def backprop(node) -> None:
    value = node.value
    while node:
        node.N += 1
        node.W += value
        node = node.parent


def uct(node, c) -> float:
    return node.W / node.N + c * math.sqrt(math.log(node.parent.N) / node.N)


def mcts(verifier, budget, rng, c=1.4) -> Optional[str]:
    root = Node((START, ()))
    evaluate(root, verifier)
    backprop(root)
    while verifier.calls < budget:
        node = root
        while node.children and node.full() and not node.terminal:      # SELECT
            node = max(node.children, key=lambda n: uct(n, c))
        if not node.terminal:                                            # EXPAND
            if node.untried is None:
                node.untried = list(range(len(OPS)))
                rng.shuffle(node.untried)
            if node.untried:
                child = Node(step(node.state, node.untried.pop()), node)
                node.children.append(child)
                evaluate(child, verifier)                                # EVALUATE
                node = child
        backprop(node)                                                   # BACKPROP
        if node.solved:
            return render(node.state)
    return None


# ---------------------------------------------------------------------------
# The baseline: best-of-N. SAME policy (uniform), SAME verifier, SAME budget —
# but no tree. Each attempt is independent from the root, abandoning a line the
# verifier proves dead. It cannot reuse a good prefix or shift budget toward it.
# ---------------------------------------------------------------------------

def best_of_n(verifier, budget, rng) -> Optional[str]:
    while verifier.calls < budget:
        state = (START, ())
        for _ in range(MAX_DEPTH):
            if verifier.solved(state):
                return render(state)
            if not verifier.alive(state):
                break                                  # dead line, start a new attempt
            state = step(state, rng.randrange(len(OPS)))
        if verifier.solved(state):
            return render(state)
    return None


# ---------------------------------------------------------------------------

def compare(budget=300, seeds=40):
    rows = []
    for name, search in (("MCTS", mcts), ("best-of-N", best_of_n)):
        wins, calls_to_win = 0, []
        for seed in range(seeds):
            v = Verifier()
            sol = search(v, budget, random.Random(seed))
            if sol:
                wins += 1
                calls_to_win.append(v.calls)
        med = sorted(calls_to_win)[len(calls_to_win) // 2] if calls_to_win else None
        rows.append((name, wins, seeds, med))
    print(f"build {TARGET} from {START}; budget = {budget} verifier calls, "
          f"{seeds} seeds; same policy + verifier for both\n")
    print(f"  {'method':10}  {'solved':>10}  {'median calls to solve':>22}")
    for name, wins, total, med in rows:
        print(f"  {name:10}  {wins:>5}/{total:<4}  {str(med) if med else '—':>22}")


if __name__ == "__main__":
    sol = mcts(Verifier(), budget=300, rng=random.Random(0))
    print("one MCTS solution:", sol, "=", eval(sol) if sol else None, "\n")
    compare()
