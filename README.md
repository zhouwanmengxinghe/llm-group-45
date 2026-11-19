# PatchLab: A Test-Driven Autonomous Debugging and Software Repair Agent

COMP7608B, Group 45. Zhu Wenpu (3036793380), Ma Jinghan (3036791409), Hou Yifu (3036898738).

PatchLab is a local Python repair workbench. One model-driven controller chooses inspection tools, proposes source edits, observes real test results and stops within explicit budgets. The browser supports ordinary conversation, a simple no-existing-test workflow and a professional test-driven workflow. Original projects are preserved; patches are reviewed and applied separately.

## Quick start

Install Python 3.12+ and Git. On Windows double-click `start.cmd`. On macOS run `bash start.command` (or `chmod +x start.command` once and double-click it). The launcher creates `.venv`, installs pytest and opens the local browser. A terminal runs the local service and controller; closing it stops the service. Select the default DeepSeek provider and enter its API key, or select another compatible provider and specify the complete chat-completions URL, deployment name and key. A paid model account and internet access are required for live chat/repair. Startup without a key still opens the interface.

The default model is the service alias `deepseek-flash`, not a pinned immutable model checkpoint. The default endpoint is `https://api.deepseek.com/chat/completions`. Other providers may need `thinking` removed and JSON mode disabled. See `configs/model.example.toml`; keys belong in the named environment variable, never committed configuration. Windows saved keys use current-user DPAPI. macOS saved keys are plaintext with owner-only permissions. Never include either local key file in a submission.

The browser binds to loopback and uses a local access token. Logs are stored under `runs/`. Repository content and selected logs are sent to the configured model provider; do not use confidential repositories without permission. Historical runs can contain private paths and task text.

## Use the workbench

Ordinary chat uses session context and model-assisted compression. Select Repair task for code changes. Simple mode requires the project path and an observed problem; reproduction steps and startup commands help. The controller must establish a failing behavioral reproducer before claiming a simple-mode repair. Startup commands are context, not arbitrary shell tools. Simple-mode tests execute on the host and require a trusted project.

Professional mode takes a project/revision, editable source allowlist, target tests and regression selectors. The browser defaults to `WORKTREE`, which snapshots current files including previously applied changes. Enter `HEAD` or a commit for a fixed Git snapshot. Supply an existing compatible Docker image for isolated tests, or explicitly trust local execution. Docker images must already contain project dependencies; network access is disabled during container tests. Passing a selected regression subset does not establish full-project correctness.

`verified` means the supplied local checks passed. It is not proof that every bug is fixed. In either browser repair mode, **Review each candidate before testing** is enabled by default. A candidate pauses the worker and shows its diagnosis and diff. **Approve and test** permits candidate verification; **Reject candidate** returns reviewer feedback so the agent can revise or stop. Initial tests and reproducer checks still run before candidate review. An unanswered review expires after 15 minutes and stops the task. Clear the checkbox for automatic candidate testing. CLI `--approve` continues to provide its existing review gate.

After required local checks pass, the result card offers **Apply patch to project**. This separate confirmed action updates only the recorded Python source files, checks every preimage before writing and preserves originals under the run's `apply-backup/`. Files changed since the repair are rejected; CRLF line endings are preserved. A failed multi-file write attempts rollback and reports the backup location. Application is serialized against other browser tasks on the same project and does not create a Git commit. Repeating the same apply request returns its saved receipt without rewriting files. Follow-up browser tasks default to `WORKTREE` so they include the applied edits; selecting `HEAD` intentionally uses committed source instead. Changes made outside PatchLab should be paused while applying. Older runs without application metadata can still be applied manually after review using `git apply --check /path/to/final.patch`, then `git apply /path/to/final.patch`.

## Reproducible examples and checks

After startup has installed the environment, use its Python (`.venv/Scripts/python.exe` on Windows; `.venv/bin/python` on macOS):

```sh
python examples/run_examples.py --output runs/my-examples
python -m pytest -q
python -m patchlab demo --trusted-local --output runs/demo --mode memory
```

Use a new output directory each time. These commands execute trusted bundled fixtures locally. The first and third commands use a scripted model and no API. Add `--live` to the example command for paid live-model normal and changed-request cases. The deliberately repeating failure model stays scripted. See `examples/README.md` for inputs, expected outcomes and genuine recorded traces. Optional Docker integration checks require an image and explicit opt-in; a skipped integration test is not a passing Docker result.

## Experiments and records

`single`: at most one effective candidate. `feedback`: up to five candidates with recent test feedback. `memory`: up to five with a structured failure ledger. All can inspect tools before proposing a candidate. Repeated patches consume calls/tokens but not effective candidates; three repeats without a new candidate stop the controller. Session summaries, raw context archives and the task failure ledger serve different purposes.

The latest uniform 30-task evaluation resolved 21/30, 19/30 and 22/30 respectively, using one run per task/condition. Ten tasks were development tasks; twenty were deliberately selected and environment-checked. This is not a random independent benchmark-wide holdout. See `docs/reports/Validation30_Report_EN.md` and `evaluation/` for per-task results and source hashes. Local verification and withheld-test resolution are different fields. Shared pre-candidate inputs reduced physical API usage; equivalent tokens are the appropriate standalone workload comparison.

The final report is `docs/reports/PatchLab_Final_Report_EN_Illustrated.pdf`; its editable Word version is alongside it. See `HANDOFF.md`, `AI_USE_DECLARATION.md` and the selected final development prompt record, `ai_records/recoverable_project_prompts_en.md`. Runtime system prompts are exported separately in `ai_records/runtime_prompts.json`. The English submission ZIP includes the report, source, runnable examples, traces and evaluation records. Private Chinese review files and superseded prompt drafts are excluded.

Windows execution was tested. macOS launcher behavior was checked with simulated platform tests, not a physical Mac. Python/target-project dependencies and Docker image architectures must be verified on the destination machine.

Release checks: after adding browser approval and patch application, 86 tests passed and one Windows symlink test was skipped because link-creation permission was unavailable. Both Docker integration checks passed using the existing local image. An isolated browser smoke test completed candidate approval, real test execution and explicit patch application with backup verification; it used a scripted model without paid API calls. Details: `evaluation/release-checks.json`.
