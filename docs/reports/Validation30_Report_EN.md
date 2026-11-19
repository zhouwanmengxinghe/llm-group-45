# Updated controller uniform 30-task retest

All 30 tasks and all three conditions are retained. The pilot10 was used to diagnose the controller; the new20 is a deliberately selected cohort with 10 short and 10 medium human repair-time labels. This is not a random untouched benchmark-wide holdout. The same model, 16-decision ceiling, 1,200-token response ceiling and candidate limits 1/5/5 apply to every condition. Repeated patches consume calls and tokens, but not effective candidates; three repeats without a novel candidate stop the run.

The old public SymPy15017 rank-zero length assertion contradicts the issue. Its entire node was excluded before this retest for every condition, while other original regressions and all official acceptance tests remain unchanged. Original and reference public-suite checks passed. No official grading feedback was supplied to the Agent, and tasks/configuration were not changed according to observed outcomes.

| Condition | Resolved/30 | Pilot10 | New20 | Equivalent tokens | Actual tokens | Duplicates blocked |
| --- | --- | --- | --- | --- | --- | --- |
| single | 21/30 | 7/10 | 14/20 | 479,479 | 479,479 | 0 |
| feedback | 19/30 | 6/10 | 13/20 | 592,028 | 217,241 | 10 |
| memory | 22/30 | 7/10 | 15/20 | 606,927 | 236,196 | 11 |

| Instance | Single | Feedback | Memory |
| --- | --- | --- | --- |
| pytest-dev__pytest-5262 | resolved | resolved | resolved |
| pytest-dev__pytest-6202 | resolved | resolved | resolved |
| pytest-dev__pytest-7432 | resolved | resolved | resolved |
| sympy__sympy-15017 | unresolved | unresolved | unresolved |
| sympy__sympy-15345 | resolved | unresolved | resolved |
| sympy__sympy-15809 | resolved | resolved | resolved |
| sympy__sympy-16886 | resolved | resolved | resolved |
| sympy__sympy-18763 | unresolved | unresolved | unresolved |
| sympy__sympy-19637 | resolved | resolved | resolved |
| sympy__sympy-20916 | unresolved | unresolved | unresolved |
| django__django-10999 | unresolved | unresolved | unresolved |
| django__django-11099 | resolved | resolved | resolved |
| django__django-11119 | resolved | resolved | resolved |
| django__django-11133 | resolved | unresolved | resolved |
| django__django-11163 | resolved | resolved | resolved |
| django__django-11880 | resolved | resolved | resolved |
| django__django-12276 | resolved | resolved | resolved |
| django__django-13023 | resolved | resolved | resolved |
| django__django-14089 | resolved | resolved | resolved |
| django__django-14373 | resolved | resolved | resolved |
| django__django-11206 | unresolved | unresolved | resolved |
| django__django-11848 | resolved | resolved | resolved |
| django__django-13195 | unresolved | unresolved | unresolved |
| django__django-13670 | resolved | resolved | resolved |
| django__django-14155 | unresolved | unresolved | unresolved |
| sympy__sympy-13031 | unresolved | unresolved | unresolved |
| sympy__sympy-13647 | resolved | resolved | resolved |
| sympy__sympy-14531 | unresolved | unresolved | unresolved |
| sympy__sympy-19346 | resolved | resolved | resolved |
| sympy__sympy-20154 | resolved | resolved | resolved |

Shared prefixes reduce physical API requests in this paired experiment; equivalent tokens charge the shared workload to each condition. One run per task and condition does not establish statistical significance. A normal stagnation stop without a patch remains in the denominator. Raw trajectories, patches, usage, code hashes, configuration and independent grading reports are archived alongside these results.
