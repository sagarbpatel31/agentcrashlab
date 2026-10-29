# Three-minute demonstration

This is a recording guide, not a claim that live results have already been measured. Use the exact labels shown by the app. The included browser test recording is an offline fixture walkthrough with a developer-supplied repair.

## 0:00–0:20 — The problem

“When an agent's tool times out, did nothing happen—or did the write succeed and only its response disappear? A blind retry can create a duplicate. AgentCrashLab makes that difference visible.”

Show the local laboratory and select Workspace Provisioner.

## 0:20–0:50 — Code-aware experiment design

With an active provider, open the agent source and select Design from agent code. Show the investigator's actual output, including its source-specific rationale and fault target. Identify the Meta model used.

If credits are unavailable, show Review experiments and explicitly state: “These are our included scripted acceptance fixtures. Live investigation is not configured in this recording.” Do not substitute fixture output for model output.

## 0:50–1:30 — Failure evidence

Run the campaign. Select Response lost after commit. Show two actual workspace records, the agent's timeout observation, the committed write, the retry, and the violated one-workspace assertion.

“The agent reported a timeout. The service had already committed. The second action duplicated the workspace.”

Replay the recorded actions and explain that replay uses no fresh model inference.

## 1:30–2:20 — Repair and verification

Generate a candidate with the live investigator. Show its diff and reasoning. Verify in Modal or Docker. Show healthy control, original failure and two task variations. A failed or inconclusive candidate must be shown honestly.

For the offline walkthrough, import a developer-supplied stable-key repair, identify that provenance, and show its actual isolated verification. Do not call it an AI-generated repair.

## 2:20–2:45 — Transfer and artifacts

Select Artifact Publisher and show the analogous failure in a different workflow. Explain that its tool names and assertions differ. Export the repair ZIP and show the test, patch, and evidence files.

## 2:45–3:00 — Close

“AgentCrashLab turns a recovery bug into a counterexample, a reviewable patch, and an independently checked regression. It verifies the tested contract, not every possible future behavior.”

Show the public repository and setup instructions once published.
