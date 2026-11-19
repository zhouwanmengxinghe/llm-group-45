# Frozen thirty-task evaluation

`validation30-results.json` records the configuration, evaluated implementation hashes, all ninety outcomes and usage summaries. `validation30-results.csv` is the tabular export; `completion.json` confirms the completed cohort. The English result discussion is in `docs/reports/Validation30_Report_EN.md`.

The final illustrated report is `docs/reports/PatchLab_Final_Report_EN_Illustrated.pdf`. `development40-summary.json` and `docs/reports/historical40-index.json` preserve the forty-task development results separately. They are diagnostic development evidence, not additional validation runs.

The task identities and public revisions are in `benchmarks/validation30-public-lock.json`, the selected new-cohort metadata in `benchmarks/final30-selection.json`, and acceptance metadata in `benchmarks/reselected20-acceptance.json`. No gold patches or hidden acceptance tests are supplied to the generation controller. The experiment used separate reference/negative/public-suite checks and retained all thirty task outcomes. Original logs and image builds are large local research artifacts, not bundled dependencies.

To repeat generation, prepare clean public repository snapshots and compatible local Docker images; construct a manifest using the included SWE-bench CLI adapter (`python -m patchlab --help`), validate it, and run `batch` with the recorded budgets. Export predictions and score independently using the pinned SWE-bench evaluation environment. The ZIP does not contain all historical dependency images or the upstream benchmark dataset, so the full ninety-run benchmark is not a one-command offline replay. The bundled examples are independently runnable without that infrastructure. Historical model alias availability and exact provider outputs cannot be guaranteed.

Prefix reuse applies only to identical pre-first-candidate inputs. Actual token totals count physical API calls; equivalent totals charge reused inputs to each condition. These totals are not interchangeable. Zero scoring execution errors does not mean every repair succeeded. The controller status alone is not the independent withheld-test result. This release includes later interface/documentation changes; the evaluated source hashes identify the earlier frozen experiment, not the entire current source tree.

## Historical scoring adapter

`runtime/validation30_harness.py` is an exact copy of the adapter used for the thirty-task run. It wraps SWE-bench 5.0.2 with network-disabled containers, exact-base resets, source-import checks instead of editable reinstallation, and legacy output normalization. It retains upstream test assertions. `runtime/validation30-images.json` lists the local image names and public base revisions; it does not contain reference patches, acceptance tests or image binaries. These are prepared local images, rather than an unmodified official-image experiment.

For an independent replay, obtain the upstream dataset for the selected IDs in a separate grading workspace, prepare compatible images, and build a private dataset JSON containing its evaluation fields plus each row's mapped `image`. Keep that file away from the generation controller. With SWE-bench 5.0.2 and Docker installed in the grading environment, run from that separate workspace:

```sh
python /path/to/submission/evaluation/runtime/validation30_harness.py -d /path/to/private-grading-runtime.json -p /path/to/predictions.jsonl -i TASK_ID -id replay --max_workers 1 --timeout 240 --report_dir /path/to/score-output
```

The upstream dataset and prepared images are prerequisites; the public image map alone is not a runnable grading dataset. The adapter writes the original and adapted environment scripts and raw output for audit. Reference patches and withheld test contents remain excluded from the submission and from model inputs.
