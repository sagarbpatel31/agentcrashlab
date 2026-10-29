# AgentCrashLab — submission draft

**Tagline:** Find the failure. Prove the fix.

**Track:** Indie Developer. **Theme:** Build for Your World; software reliability also aligns with Push the Frontier.

## Problem

Tool-using agents can take incorrect actions while appearing to recover successfully. A service may commit a write but lose its response. Retrying can duplicate the action. Ordinary happy-path demos and transcript-only evaluations can miss the difference between an observation and an effect.

## What we built

AgentCrashLab combines a local dashboard and CLI, a Python experiment controller, an eve investigator connected directly to Meta model providers, replayable evidence, and isolated verification of candidate code repairs. It ships workspace provisioning and artifact publishing examples with explicit task contracts.

## Meta integration

The investigator uses Meta models to inspect source, design targeted experiments, analyze failure evidence and propose replacement source. The host validates the output and evaluates the actual simulated service state. Meta, Baseten and Fireworks are distinct, explicitly configured inference routes. Modal and Docker provide isolated execution.

## Original contribution

All application source in this repository was created during the hackathon. Existing open-source frameworks and libraries are declared dependencies. Fault injection and replay have prior art; our work integrates source-aware experiment design, counterexample reduction, candidate repairs and engine-owned verification in a local developer workflow.

## Validation and limitations

Use docs/verification.md for the actual checks completed. Offline fixtures and handwritten references are labeled separately from live models and generated repairs. Report live success rates only after running documented campaigns; do not extrapolate from offline fixtures. Arbitrary production systems and all possible failure states are outside the MVP.

## Before submission

- Add the final public repository and accessible demo-video URLs.
- Record live source-aware investigation and repair if credits are active.
- Check the original-contribution explanation and provider/model identities in the recording.
- Include only actual verification results; retain failed and inconclusive outcomes.
