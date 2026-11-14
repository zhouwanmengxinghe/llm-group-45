# SWE-bench Verified pilot preparation

This integration separates patch generation from official scoring. PatchLab
receives the repository at the base commit, the public problem statement, an
operator-selected Python source allowlist, and public regression tests. It does
not receive the reference fix, test patch, official test lists, hints, or grader
output. A patch that preserves the public suite is recorded as
`candidate_ready`, not `verified`. Only the upstream SWE-bench harness may mark
the task resolved.

No live SWE-bench task has been run yet. The files and commands below prepare a
single-instance pilot and deliberately stop before model calls or official
evaluation.

The public-suite environment check completed on 2026-11-14 using Docker Desktop
on an ARM64 Mac with the upstream AMD64 image under emulation. SymPy's public
`test_basic.py`, `test_symbol.py`, and `test_boolalg.py` suites completed in
about 34 seconds: 103 passed, 1 skipped, and 1 expected failure. This validates
the generation environment only; it is not a model result or official score.

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

Validate this manifest before any model call. Validation may run public project
tests, so it belongs to the test phase and has not been executed yet.

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
harness:

```bash
python -m patchlab swebench-eval-plan \
  --lock benchmarks/swebench-pilot-lock.json \
  --predictions /path/to/predictions.jsonl \
  --task-repo /path/to/swe-bench-tasks \
  --run-id patchlab-pilot-01 --workers 1 \
  --output /path/to/evaluation-plan.json
```

Review disk, memory, architecture, image source, and run ID before executing the
saved command. The upstream documentation recommends substantial Docker disk
space and memory. On Apple Silicon, build from the pinned task repository rather
than assuming the published x86-64 image can run natively.

## Stop point and remaining decisions

Preparation currently stops before:

1. cloning the SymPy and Astropy source repositories;
2. selecting public regression tests and editable source allowlists;
3. installing the upstream SWE-bench CLI and building task images;
4. validating the public suites;
5. calling DeepSeek;
6. running the official grader.

Before those steps, decide whether the first pilot should use only the upstream
SymPy quick-start task, whether to build locally or use a compatible published
image, and how much disk space may be used.

