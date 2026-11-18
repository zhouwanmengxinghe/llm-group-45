# SWE-bench Verified pilot preparation

This integration separates patch generation from official scoring. PatchLab
receives the repository at the base commit, the public problem statement, an
operator-selected Python source allowlist, and public regression tests. It does
not receive the reference fix, test patch, official test lists, hints, or grader
output. A patch that preserves the public suite is recorded as
`candidate_ready`, not `verified`. Only the upstream SWE-bench harness may mark
the task resolved.

The files and commands below define the reproducible single-instance pilot.
Live single, feedback, and memory development runs have exercised the complete
generation and official-evaluation path; they remain smoke evidence rather than
a formal experiment.

The public-suite environment check completed on 2026-11-14 using Docker Desktop
on an ARM64 Mac with the upstream AMD64 image under emulation. SymPy's public
`test_basic.py`, `test_symbol.py`, and `test_boolalg.py` suites completed in
about 34 seconds: 103 passed, 1 skipped, and 1 expected failure. This validates
the generation environment only; it is not a model result or official score.

## First end-to-end result

The first live run completed on 2026-11-14 with the `deepseek-flash` provider
alias in `single` mode. The agent made eight model calls, including three valid
inspection actions, reported 21,876 tokens, and submitted one candidate after
about 76 seconds. Four intermediate model responses were invalid actions, but
the controller continued within its fixed call budget.

The candidate added an empty `__slots__` declaration to `Printable` in
`sympy/core/_print_helpers.py`. All 103 selected public regression tests passed
after the edit. The pinned upstream SWE-bench harness then applied the patch in
a clean instance container and reported the task as **resolved**: the one
FAIL_TO_PASS test and all 21 PASS_TO_PASS tests succeeded. There were no patch
application, infrastructure, container-cleanup, or grading errors.

This is one pilot task and therefore demonstrates integration, not a benchmark
success rate or evidence that the iterative conditions outperform `single`.

## Next three SymPy tasks

The next development batch is frozen before any model run in
`benchmarks/swebench-sympy-next3-selection.json`. It excludes the completed
pilot, keeps SymPy Verified tasks labelled below one hour, sorts by instance ID,
and selects the first three: `sympy__sympy-11618`, `sympy__sympy-12096`, and
`sympy__sympy-12419`. This deterministic rule prevents replacing tasks based on
model success or failure. The batch remains development evidence and is not the
final multi-repository sample.

## Frozen pilot

The pilot selection is stored in
`benchmarks/swebench-pilot-selection.json`. It pins:

- dataset: `SWE-bench/SWE-bench_Verified`, test split;
- dataset revision: `78f471bf655a3137b2e8a75af1501690ec009ec3`;
- upstream task repository revision:
  `3d07b464b7b311a0cbfb5ed5b2d8a3b96f84a33d`;
- instance: `sympy__sympy-20590`.

This is the upstream quick-start example. It is an infrastructure pilot, not a
representative or final sample.

`benchmarks/swebench-pilot-lock.json` was generated from a sparse checkout of
the pinned official task repository. The lock contains only public metadata and
problem statements plus content hashes. It lists every withheld artifact under
`generation_excludes`.

To reproduce the lock from a pinned task-repository checkout:

```bash
python -m patchlab swebench-freeze \
  --task-repo /path/to/swe-bench-tasks \
  --selection benchmarks/swebench-pilot-selection.json \
  --output benchmarks/swebench-pilot-lock.json
```

## Prepare generation workspaces

Before running the model, clone each source repository and keep it at the
locked base commit. Copy
`benchmarks/swebench-pilot-workspaces.example.json` outside the repository and
replace each placeholder with:

- the local Git checkout;
- production Python files selected from the issue and repository inspection,
  without consulting the gold patch;
- public regression tests that do not include the upstream `test.patch` or
  `tests.json` contents.

Then create a normal PatchLab batch manifest:

```bash
python -m patchlab swebench-manifest \
  --lock benchmarks/swebench-pilot-lock.json \
  --workspaces /path/to/pilot-workspaces.json \
  --output /path/to/swebench-pilot-manifest.json
```

Validate this manifest before any model call. Validation runs only the selected
public project tests and must succeed on the frozen baseline.

```bash
python -m patchlab validate-manifest \
  --manifest /path/to/swebench-pilot-manifest.json \
  --image swebench/sweb.eval.x86_64.sympy_1776_sympy-20590:latest \
  --container-python /opt/miniconda3/envs/testbed/bin/python \
  --test-program "bin/test -C --no-colors"
```

The pilot uses the instance image recorded in the lock. Its Conda interpreter
is selected with `--container-python /opt/miniconda3/envs/testbed/bin/python`.
SymPy 1.7 does not include pytest in this image, so its public tests use the
repository's bounded `bin/test` program.

## Export and official evaluation

After a PatchLab batch finishes, convert one condition and repeat to official
prediction JSONL:

```bash
python -m patchlab swebench-export \
  --lock benchmarks/swebench-pilot-lock.json \
  --batch-output /path/to/batch \
  --mode single --repeat 1 --model-name patchlab-deepseek-flash \
  --output /path/to/predictions.jsonl
```

Finally, write a reviewable evaluation plan. This command does not invoke the
harness. Omit `--task-repo` when the pinned published image is already present;
pass it only when deliberately building from the pinned task repository.

```bash
python -m patchlab swebench-eval-plan \
  --lock benchmarks/swebench-pilot-lock.json \
  --predictions /path/to/predictions.jsonl \
  --run-id patchlab-pilot-01 --workers 1 \
  --output /path/to/evaluation-plan.json
```

After the official harness writes `results.json`, validate and attach it to the
batch, then rebuild the CSV and mode summary automatically:

```bash
python -m patchlab swebench-record-score \
  --lock benchmarks/swebench-pilot-lock.json \
  --batch-output /path/to/batch \
  --official-results /path/to/results.json \
  --mode single --repeat 1
```

Review disk, memory, architecture, image source, dataset revision, and run ID
before executing the saved command. Published x86-64 images require an AMD64
compatibility check on Apple Silicon.

## Iterative-mode smoke result

On 2026-11-16, feedback and memory were independently run on the same frozen
pilot with `deepseek-flash`, thinking disabled, JSON mode enabled, a 16-decision
limit, a five-candidate limit, and a 1200-token completion limit. Each mode used
two decisions and one candidate, passed all 103 selected public tests, and was
reported resolved by the pinned official harness. This confirms integration
only: the task was already used in development and the two modes did not need
to recover from a failed candidate.

Before formal runs, freeze a new result-independent task selection, public-test
and editable-source rules, model configuration, timeouts, API budget, and Docker
disk budget. Run every condition on exactly the same instances and retain empty
patches and failures.
