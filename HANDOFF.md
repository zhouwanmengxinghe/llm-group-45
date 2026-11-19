# Group 45 handoff

Project: PatchLab, A Test-Driven Autonomous Debugging and Software Repair Agent.
Members: Zhu Wenpu (3036793380), Ma Jinghan (3036791409), Hou Yifu (3036898738).

## Source map

`bootstrap.py` and platform launchers configure the local environment and model. `patchlab/web.py` and `webui.html` implement the browser workspace. `decision.py` holds the OpenAI-compatible provider adapter and runtime prompts. `experiment.py` runs professional repairs; `simple.py` handles projects without supplied tests. `workbench.py` implements frozen snapshots, bounded file inspection, exact edits and test execution. `repair_memory.py` stores failed hypotheses. `memory.py` compresses repair context while retaining original archives. `resilience.py` bounds transient retries. `batch.py`, `paired.py` and `swebench.py` implement experiment orchestration, exact-input prefix reuse and independent scoring adapters.

## What is implemented

Model-selected tools, test-feedback repair, failure memory, session persistence, context compression, raw-context archiving, event traces, API retries, candidate budgets, repeated-patch recovery/stopping, source allowlists, frozen test contracts, optional Docker execution, CLI approval and a browser workspace. The three submission examples are independently runnable. The latest 30-task experiment contains all 90 task/condition results, including unresolved tasks.

## Limits and remaining human work

The English final report is translated from the saved Chinese Word master and included in PDF and editable Word form. The selected final project prompt record is `ai_records/recoverable_project_prompts_en.md`. Confirmed responsibilities are Hou Yifu: core/model/memory; Zhu Wenpu: tools/environments; Ma Jinghan: data/experiments. The final package includes source, reports, examples, traces, results and a file-hash manifest.

Before upload, the members should review the English report and AI-use declaration and rehearse startup and the live demonstration on the presentation machine. Upload the report PDF and source ZIP separately as required. Prepare the two-minute pitch and live changed-request demonstration; all members must attend. The supplied guide states 25 November 2026, 23:59 Hong Kong time as the deadline and 1 or 8 December for assigned presentations. Check Moodle for the assigned slot, any later announcement and the published marking rubric.

Browser repair now offers candidate review before testing and a separate confirmed application action for passing patches. `patch_application.py` validates current source against recorded preimages, saves backups and records application receipts. `WORKTREE` snapshots include applied but uncommitted changes; a chosen Git commit still freezes that revision. These interface/application additions postdate the recorded thirty-task experiment; its results and hashes remain unchanged.

No Java/Defects4J extension, no full-project correctness guarantee and no physical-Mac acceptance test. Generated test oracles can be wrong; inspect them before trusting a repair. First candidates were not identical in every experimental pair, so the observed difference is not a clean causal estimate of iteration alone. Local snapshots do not make host execution a security sandbox.

## For coding assistants

Read the current README and frozen evaluation metadata first. Do not modify hidden acceptance tests, relabel failures, remove unresolved tasks, expose provider keys or claim scripted runs are live model evidence. Preserve raw experiment data and source hashes. Do not merge the private Chinese review directory into the submission. A source translation or UI revision after the experiment is not the historical evaluated snapshot; retain that distinction in any report. Per-person ownership cannot be inferred from generated files or this handoff.
