# Three runnable submission examples

Run `python examples/run_examples.py --output runs/a-new-directory` from the project root using the installed environment. Prerequisites: Python 3.12+, Git and pytest. This default uses scripted decisions but real repository snapshots, patch construction and pytest execution. It is a deterministic controller demonstration, not a model-quality experiment. Add `--live` to use the configured paid model for the first two tasks. Existing output is never overwritten.

## 1. Ordinary repair

Input: "Reversed intervals must return zero; positive intervals must retain their duration in seconds."
The fixture contains `duration(start, end) = end - start`. Target: `test_empty`; regression: both positive and reversed intervals. Expected: original target fails, model inspects source, proposes `max(0, end - start)`, target and regression pass, status `verified`. Original fixture is unchanged until the example operator explicitly applies the accepted patch for the next case.

## 2. Changed request

Input: "Changed request: duration inputs remain seconds, but return minutes, including fractional minutes. Reversed intervals still return zero."
The example operator applies the first accepted patch to a disposable fixture, changes and commits the public contract, and starts a new task with the previous decision as session context. Expected: seconds-based implementation fails the new target, the repair divides the clamped duration by 60, all three updated tests pass. This explicit setup is required; the web application does not silently carry patches into subsequent source snapshots.

## 3. Failure and bounded stopping

Input: the original reversed-interval defect; fault injection: a scripted model repeatedly proposes `return 0`.
Expected: target passes but the positive-interval regression fails. Three further identical patches are blocked. Status `stagnated`, one effective candidate, three duplicates, no final verified patch. The model is deliberately scripted even with `--live`; test outputs and controller events are real. No real model provider request or token usage is claimed for scripted calls. Legacy `provider_requests` fallback counters in scripted result files count controller decisions, not network requests.

## Recorded evidence

The default command generates fresh deterministic traces in the requested output directory. `traces/live/`, when present, contains actual provider-generated decisions for normal/changed requests and the labelled scripted failure injection. Each case includes `result.json`, `events.jsonl`, `contexts.jsonl`, applicable patches and failure memory. `examples-summary.json` records provenance and setup. Machine-local paths are replaced with placeholders in exported traces; behavioral output, decisions and metrics are preserved. Raw originals remain private under `runs/`.

Inspect `events.jsonl` in order: initial failure, inspection, proposal, target result, regression result, completion. Read `final.patch` and both test results before accepting a `verified` result. Live generations may vary; the exact recorded outcome is evidence for that run only.
