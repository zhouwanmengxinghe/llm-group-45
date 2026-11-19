# Sources and third-party components

PatchLab is coursework by COMP7608B Group 45. The project proposal and course student guideline determine the intended scope and deliverables; they are not source-code licenses. Member responsibilities are stated in the final report.

- SWE-bench and its Verified dataset provide public defect descriptions, base revisions and independent acceptance tests: https://github.com/SWE-bench/SWE-bench and https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified . Task revisions and provenance are recorded in the benchmark metadata. Upstream gold patches and withheld test content are excluded from the source snapshot and generation inputs.
- QuixBugs supplies the small development tasks under `examples/quixbugs/`: https://github.com/jkoppel/QuixBugs . These are attributed development fixtures rather than original defects authored by the group. Consult the upstream repository for license terms before redistributing a modified task corpus.
- pytest executes the local checks; its pinned development version is in `requirements-dev.txt`: https://github.com/pytest-dev/pytest . Python standard-library facilities implement most of the controller and web service: https://www.python.org/ .
- Docker supplies the optional isolated test executor: https://www.docker.com/ . Base image and task dependencies retain their respective upstream licenses. The small historical build wheels under `benchmarks/requests-network/build-wheels/` retain embedded package metadata/licenses; hashes and origins are in `SHA256.json`. They support legacy benchmark environments rather than the normal host installation.
- The DeepSeek API is an external paid model service: https://api-docs.deepseek.com/ . Runtime provider configuration is separate from project authorship. The recorded service alias is not an independently archived checkpoint.
- Writing guidance: https://github.com/syw2039/humanizer-zh . AI assistance and partial prompt-record availability are described in `AI_USE_DECLARATION.md`.

The team should verify final license compliance, reference formatting and its own contribution statement before submission. This source list does not replace upstream license notices.
