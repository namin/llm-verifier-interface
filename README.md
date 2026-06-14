# The LLM-Verifier Interface

Based on lectures on the LLM-Verifier Interface at the Summer School on Foundations of Programming and Software Systems (FoPSS 2026).
See the [abstract](abstract.md).

## Agents like Claude Code

- [agent.py](agent.py): the essence of an agentic loop in Python
- [dafny_agent.py](dafny_agent.py): shows how to add an explicit tool for Dafny to the agent
- [henri](https://github.com/metareflection/henri): a slightly bigger agentic loop in Python
- [henri-lemmascript](https://github.com/midspiral/henri-lemmascript): a port of henri to [LemmaScript](https://github.com/midspiral/LemmaScript)
- [pi](https://github.com/earendil-works/pi): an extensible AI agent toolkit in TypeScript
- [opencode](https://github.com/anomalyco/opencode): an open source coding agent in TypeScript

## Verifier in the Loop

- [verifier_loop.py](verifier_loop.py): generate, verify, retry until Dafny accepts
- [VerMCTS](https://github.com/namin/llm-verified-with-monte-carlo-tree-search): the retry generalized to Monte Carlo tree search on partial programs guided by the verifier
- [COPRA](https://github.com/trishullab/copra): tactic-by-tactic proving in Lean or Rocq, with error feedback and backtracking
- [CEGIS](https://people.csail.mit.edu/asolar/SynthesisCourse/Lecture17.htm): the classical loop: propose, verify, accumulate counterexamples
- [cegis.py](cegis.py): CEGIS with an LLM as the synthesizer and Z3 as the verifier — the verifier returns a concrete counterexample on every failure, and they accumulate into the spec; the accumulation is the part [verifier_loop.py](verifier_loop.py) leaves out

## Decomposition

- [Draft, Sketch, and Prove](https://arxiv.org/abs/2210.12283): informal proofs guide formal proof sketches; the sketch's holes need only each other's statements, not each other's proofs
- [POETRY](https://arxiv.org/abs/2405.14414): recursive level-by-level proving: sketch with `sorry` placeholders, then solve each hole; the longest proof found grows from 10 to 26 lines
- [LEGO-Prover](https://arxiv.org/abs/2310.00656): proven lemmas accumulate into a growing library of reusable skills

## Autoformalization

- translating from informal to formal: for example, a word problem into a query for an SMT solver
- [claimcheck](https://github.com/metareflection/claimcheck): Dafny verifies proofs; claimcheck confirms intent — round-trip informalization, blinded, then compared against the requirement
- [Clover](https://github.com/ChuyueSun/Clover): faithfulness by triangulation: generated code, specs, and docstrings must agree
- [CLEVER](https://github.com/trishullab/clever): the end-to-end benchmark: synthesize spec, code, and proof in Lean — 1 of 161 solved at introduction

## Verifying in Mainstream Languages

- [LemmaScript](https://github.com/midspiral/LemmaScript): verifying TypeScript, via Dafny or Lean
- [Verus](https://github.com/verus-lang/verus): verifying Rust, with proofs written in Rust syntax, discharging to an SMT solver
- [Frama-C](https://frama-c.com/): verifying C, with [ACSL](https://github.com/fraunhoferfokus/acsl-by-example/blob/master/ACSL-by-Example.pdf) contracts

## Verifying Agents

- [Guardians of the Agents](https://cacm.acm.org/practice/guardians-of-the-agents/): prompt injection is mixing code and data; have the LLM plan first, verify the plan, then execute (Meijer, CACM 2026)
- [guardians](https://github.com/metareflection/guardians): a Python implementation: taint analysis, security automata, and Z3 preconditions on agent plans
- [guardians-lemmascript](https://github.com/midspiral/guardians-lemmascript): the checks themselves proved sound in Dafny via LemmaScript; can be wired into henri-lemmascript

## Self-Improving Agents

- [Darwin Gödel Machine](https://arxiv.org/abs/2505.22954): benchmark-gated self-edits
- [SICA](https://arxiv.org/abs/2504.15228): a coding agent that rewrites its own implementation
- [STOP](https://arxiv.org/abs/2310.02304): a scaffolding program that improves itself, utility-gated
- [Gödel Agent](https://arxiv.org/abs/2410.04444): the agent may edit its own improvement machinery; self-destruction by editing is a documented failure mode
- [AlphaEvolve](https://arxiv.org/abs/2506.13131): evolutionary search over code, scored by an automated evaluator
- the self-edit gate: a self-modification must verify before it is adopted — adopt on green, reject and roll back
- verified self-edits become training data, closing the loop with verification for training signal

## Verification for Training Signal

- formal-disco: verified discovery systems to generate hundreds of thousands of verified programs in Dafny, Verus, Frama-C, ..., to use as training data. Inspired by [dafny-annotator](https://github.com/metareflection/dafny-annotator), which boosted Llama 3.1 8B from 15.7% to 50.6% on annotating [DafnyBench](https://github.com/sun-wendy/DafnyBench) by fine-tuning on synthetic verified programs.
- [AlphaProof](https://www.nature.com/articles/s41586-025-09833-y): reinforcement learning with the Lean kernel as the reward, on ~80 million auto-formalized statements ([insider's account](https://www.julian.ac/blog/2025/11/13/alphaproof-paper/))
- [DeepSeek-Prover-V2](https://github.com/deepseek-ai/DeepSeek-Prover-V2): subgoal decomposition bootstraps the training data, then reinforcement learning with Lean's verdict as the reward; open weights
- [Kimina-Prover](https://huggingface.co/blog/AI-MO/kimina-prover): reinforcement learning that learns to discover and reuse lemmas, composed at test time; open weights, 92.2% on miniF2F
