# The LLM-Verifier Interface

## Agents like Claude Code

- [agent.py](agent.py): the essence of an agentic loop in Python
- [dafny_agent.py](dafny_agent.py): shows how to add an explicit tool for Dafny to the agent
- [henri](https://github.com/metareflection/henri): a slightly bigger agentic loop in Python
- [henri-lemmascript](https://github.com/midspiral/henri-lemmascript): a port of henri to LemmaScript
- [pi](https://github.com/earendil-works/pi): an extensible AI agent toolkit in TypeScript
- [opencode](https://github.com/anomalyco/opencode): an open source coding agent in TypeScript

## Verifier in the Loop

- [verifier_loop.py](verifier_loop.py): generate, verify, retry until Dafny accepts
- [VerMCTS](https://github.com/namin/llm-verified-with-monte-carlo-tree-search): the retry generalized to Monte Carlo tree search on partial programs guided by the verifier
- [COPRA](https://github.com/trishullab/copra): tactic-by-tactic proving in Lean or Rocq, with error feedback and backtracking
- [CEGIS](https://people.csail.mit.edu/asolar/SynthesisCourse/Lecture17.htm): the classical loop: propose, verify, accumulate counterexamples

## Verification for Training Signal

- formal-disco: verified discovery systems to generate hundreds of thousands of verified programs in Dafny, Verus, Frama-C, ..., to use as training data. Inspired by [dafny-annotator](https://github.com/metareflection/dafny-annotator), which boosted Llama 3.1 8B from 15.7% to 50.6% on annotating [DafnyBench](https://github.com/sun-wendy/DafnyBench) by fine-tuning on synthetic verified programs.
- [AlphaProof](https://www.nature.com/articles/s41586-025-09833-y): reinforcement learning with the Lean kernel as the reward, on ~80 million auto-formalized statements ([insider's account](https://www.julian.ac/blog/2025/11/13/alphaproof-paper/))
- [DeepSeek-Prover-V2](https://github.com/deepseek-ai/DeepSeek-Prover-V2): subgoal decomposition bootstraps the training data, then reinforcement learning with Lean's verdict as the reward; open weights