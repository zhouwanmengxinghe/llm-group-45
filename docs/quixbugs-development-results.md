# QuixBugs development results

This note records the first live-model checks of PatchLab's batch runner. These
runs are development evidence, not final benchmark results. They were used to
exercise the workflow, identify weak tasks, and check that reports contain the
measurements required by the proposal.

## Configuration

- Date: 2026-11-14
- Model endpoint alias: `deepseek-flash`
- Container image: `patchlab-quixbugs:dev`
- Repeats: one per task and condition
- Human approval: disabled
- Candidate limit: one in `single` mode and five in `feedback` mode
- Success criterion: the supplied target test and regression suite both pass

The provider alias may change over time, so the final experiment must record
the concrete model version exposed by the provider. One repeat on a development
set is not sufficient for a statistical comparison.

## Results

| Task set | Mode | Runs | Verified | Rate | Median time | Median model calls | Median reported tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original five-task development set | Single | 5 | 5 | 100% | 4.452 s | 2 | 1,456 |
| Original five-task development set | Feedback | 5 | 5 | 100% | 4.145 s | 2 | 1,458 |
| Ten additional development tasks | Single | 10 | 9 | 90% | 4.364 s | 2 | 1,648 |
| `lcs_length` follow-up | Feedback | 1 | 0 | 0% | 15.188 s | 6 | 6,839 |

The original five tasks were solved by the first candidate in both conditions.
They therefore exhibit a ceiling effect and do not test whether feedback helps
after a failed patch. The ten additional tasks provide more variety, but they
are still a development set selected before the final benchmark design.

## `lcs_length` failure

The single-attempt run failed on `lcs_length`. A focused feedback run then used
all five candidate attempts without passing the target test. The original
program returned `1` for the supplied `witch`/`sandwich` case, while all five
candidate patches returned `4` instead of the expected `2`.

This was not an API quota or execution failure. The repeated value suggests
that the model converged on the conventional longest-common-subsequence
interpretation and did not infer the benchmark function's intended semantics
from the available evidence. The trajectory is useful as a failure-analysis
case: additional attempts alone did not diversify the hypothesis.

## Conclusions and next steps

1. Keep the original five tasks as smoke tests rather than evidence for the
   research hypothesis.
2. Use harder tasks with at least one failed first candidate to measure recovery
   from feedback.
3. Run all three conditions (`single`, `feedback`, and `memory`) with the same
   frozen tasks, model configuration, and budgets.
4. Add repeated runs or fixed seeds where the model API permits them.
5. Freeze the SWE-bench Verified subset and independent grading procedure before
   collecting the final results promised in the proposal.
6. Preserve failure trajectories and classify semantic misunderstanding,
   localization, invalid patch, regression, environment, and budget failures.

