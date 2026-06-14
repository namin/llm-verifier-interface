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
- [mcts.py](mcts.py): the search pillar in miniature — MCTS with the verifier in place of the rollout (prune the provably dead, optimistically value the still-feasible); a controlled head-to-head shows it beat best-of-N at equal policy, verifier, and budget, on structure alone
- [ChopChop](https://arxiv.org/abs/2509.00360): the verifier moves *into the decoder* — constrained decoding that only emits programs satisfying a semantic property (equivalence to a reference, type safety), cast as a realizability problem solved by coinduction; correct-by-construction instead of generate-then-check (Nagy, Zhou, Polikarpova, D'Antoni, POPL 2026)
- [COPRA](https://github.com/trishullab/copra): tactic-by-tactic proving in Lean or Rocq, with error feedback and backtracking
- [CEGIS](https://people.csail.mit.edu/asolar/SynthesisCourse/Lecture17.htm): the classical loop: propose, verify, accumulate counterexamples
- [cegis.py](cegis.py): CEGIS with an LLM as the synthesizer and Z3 as the verifier — the verifier returns a concrete counterexample on every failure, and they accumulate into the spec; the accumulation is the part [verifier_loop.py](verifier_loop.py) leaves out
- [AlphaGeometry](https://www.nature.com/articles/s41586-023-06747-5): the language model only proposes auxiliary constructions; a symbolic deduction engine does the proving and the loop retries until it closes — neuro-symbolic olympiad geometry, trained from scratch on ~100M synthetic theorems, solving 25 of 30 IMO problems (Trinh et al., Nature 2024); [AlphaGeometry2](https://arxiv.org/abs/2502.03544): gold-medal level, and finds the proposer's bespoke formal language doesn't matter — a generic Gemini does as well (Chervonyi et al. 2025)
- [Lemur](https://arxiv.org/abs/2310.04870): the program-verification analog — the LLM proposes invariants as sub-goals, automated reasoners validate them, and the propose-and-validate calculus is proved sound, so the verdict holds regardless of what the LLM says (Wu, Barrett, Narodytska, ICLR 2024)

## Partial Verification

A verifier's verdict is one bit, at the end. The systems that work turn it into a dense signal over unfinished work; [verifier_loop.py](verifier_loop.py) is the baseline that doesn't. Three ways to get one:

Read the verifier's intermediate output — proof state (COPRA), still-feasible prefixes ([mcts.py](mcts.py)), accumulated counterexamples ([cegis.py](cegis.py)), discharged holes ([sketch.py](sketch.py)):
- [Baldur](https://arxiv.org/abs/2303.04910): repair from the error message, not the pass/fail bit — the model gets the theorem, the failed proof, and Isabelle/HOL's error text, and rewrites (First, Rabe, Ringer, Brun, ESEC/FSE 2023)

Learn a proxy that scores partial work, where the verifier won't:
- [GPT-f](https://arxiv.org/abs/2009.03393): an outcome objective trains the model to emit a P/N token for whether an open goal will close — provability read off the model, no value head — reordering best-first search; labels bootstrapped from the verifier over expert-iteration rounds (Polu, Sutskever 2020)
- [HyperTree Proof Search](https://arxiv.org/abs/2205.11491): a critic scores `P(provable | goal)`, and the scores multiply up an AND/OR proof hypertree to value a partial proof, driving AlphaZero-style search trained online (Lample et al., NeurIPS 2022)
- [Let's Verify Step by Step](https://arxiv.org/abs/2305.20050): grading every step beats grading only the answer — but the labels are human (PRM800K), because nothing automatic grades a half-finished argument (Lightman et al., 2023)
- [Math-Shepherd](https://arxiv.org/abs/2312.08935): automate those labels — a step's value is the fraction of rollouts from it that reach the right answer; they train the reward model and the per-step PPO signal (Wang et al. 2023)

Put the partiality in the spec, not the search:
- [Gradual Program Verification](http://www.cs.cmu.edu/~aldrich/papers/vmcai2018-gradual-verification.pdf): a contract `φ ∧ ?` is proved statically for `φ` and backed by runtime checks for `?`; adding precision only surfaces failures earlier, with the static system's soundness intact (Bader, Aldrich, Tanter, VMCAI 2018)
- [ICE](https://madhu.cs.illinois.edu/CAV14ice.pdf): learn loop invariants from examples, counterexamples, and implication pairs `(p, p′)` — the implications let the teacher flag non-inductiveness without guessing whether to add `p′` or drop `p`, which is what makes the learner converge (Garg, Löding, Madhusudan, Neider, CAV 2014)

The asymmetry: a learned proxy is gameable where a kernel verdict is not, and informal reasoning can only estimate partial credit — but a proof assistant grades fragments for free, dense and sound at once. [FoVer](https://arxiv.org/abs/2505.15960) has Z3 and Isabelle label each step (Kamoi et al., ACL 2026 Findings); [Process-Verified RL via Lean](https://openreview.net/forum?id=P00k4DFaXF) reads per-tactic credit off Lean's elaborator and folds it into the reward (Kim, Yun, ICLR 2026) — the dense form of the terminal signal [AlphaProof](https://www.nature.com/articles/s41586-025-09833-y) and [DeepSeek-Prover](https://github.com/deepseek-ai/DeepSeek-Prover-V2) use below.

## Decomposition

- [Draft, Sketch, and Prove](https://arxiv.org/abs/2210.12283): informal proofs guide formal proof sketches; the sketch's holes need only each other's statements, not each other's proofs
- [POETRY](https://arxiv.org/abs/2405.14414): recursive level-by-level proving: sketch with `sorry` placeholders, then solve each hole; the longest proof found grows from 10 to 26 lines
- [LEGO-Prover](https://arxiv.org/abs/2310.00656): proven lemmas accumulate into a growing library of reusable skills
- [sketch.py](sketch.py): Draft-Sketch-Prove in miniature — the LLM sketches the main proof against helper lemma *statements* (holes are Dafny's `assume false;`, the `sorry` analogue); each hole is then filled on its own, given only the others' statements; assemble for a fully sound proof

## Autoformalization

- translating from informal to formal: for example, a word problem into a query for an SMT solver
- vacuity: a deductive verifier silently accepts a proof that leans on contradictory assumptions — make the `requires` unsatisfiable and every `ensures` holds, so the spec passed but means nothing. Dafny flags it by tracking whether the proof ever used its goal ([`--warn-contradictory-assumptions`](https://dafny.org/blog/2023/10/27/proof-dependencies/)); the general idea is older, from detecting vacuous passes in model checking (Beer, Ben-David, Eisner, Rodeh, CAV 1997)
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
- [Language-Based Agent Control](https://arxiv.org/abs/2605.12863): the typed analog of the Guardians discipline — the agent emits Haskell programs that must type-check against developer scaffolding before they run, with effect and capability types encoding the policy (filesystem sandboxing, data provenance, information-flow control), so unsafe code is rejected at the type level before execution (Zhou, D'Antoni, Polikarpova, 2026); [Securing Agents With Tracked Capabilities](https://bracevac.org/assets/pdf/cais26.pdf) does the same in mainstream Scala 3 — capabilities are program variables and capture checking enforces local purity, keeping sub-computations side-effect-free so classified data can't leak, with no significant loss in task performance (Odersky, Zhao, Xu, Bračevac, Pham, CAIS 2026)

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
