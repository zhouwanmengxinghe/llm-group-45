# Isolated evaluation services

This adapter runs the installed upstream SWE-bench harness. It does not alter
reference patches, test patches, assertions, or resolution rules. Use a separate
grading process; never expose the grading dataset to the repair Agent.

## Why this exists

Legacy Requests tests use public HTTPBin, HTTPS certificates and a private
non-routable address for connection timeouts. Public services and modern network
proxies made the same correct patch fail or wait for 1,800 seconds. Sphinx's old
link-check tests also depend on external pages. Those are environment failures,
not evidence that an Agent repair is incorrect.

The adapter supplies HTTPBin on loopback, a disposable trusted test CA, fixed
static pages for existing Sphinx fixtures, and a real packet-drop timeout. TLS
verification stays enabled. Public egress is disabled during evaluation.
Requests containers alone receive NET_ADMIN to install their isolated firewall;
ordinary Agent test containers retain their stricter capabilities and network
restrictions.

## Offline package setup

Upstream evaluation scripts reinstall the project before running tests. The
adapter adds `--no-index --no-deps --no-build-isolation` to those installation
commands, using dependencies already in the image. For historical Astropy,
pytest and Seaborn builds, the adapter installs the fixed build tools in
`build-wheels/` first. `SHA256.json` contains the official PyPI hashes and source
URLs; each wheel is checked again before use. These wheels target Linux x86_64
Python 3.9 where a platform-specific wheel is required.

The original script and the script with offline installation flags are saved
under `evaluation-setup/`. Test commands, test patches and assertions are
unchanged. The environment also disables package indexes and version checks.
Successful test completion alone is insufficient: inspect installation output
as well, because upstream shell scripts may continue after an installation error.

Sphinx's upstream suite intentionally checks rejection of an untrusted
self-signed certificate and separately checks explicit trust configurations.
Its expected rejection message remains in the raw log when the corresponding
test passes. This is a negative TLS test, not an external certificate failure.
Do not suppress the test or disable TLS globally to remove that diagnostic.

## Build and run

Install the upstream SWE-bench harness in a separate environment, and obtain the
required task images before going offline. Build a service image for each
Requests base with this directory as its Docker build context:

Historical development grading used SWE-bench 5.0.2. This directory preserves its environment adapter and tested compatibility helpers. Large historical audit logs and image binaries are omitted. The submitted thirty-task scoring adapter and replay requirements are documented in `evaluation/README.md`.

```sh
docker build --build-arg BASE_IMAGE=swebench/sweb.eval.x86_64.psf_1776_requests-2317:latest -t patchlab-requests-network:v1 benchmarks/requests-network
docker build --build-arg BASE_IMAGE=swebench/sweb.eval.x86_64.psf_1776_requests-2931:latest -t patchlab-requests2931-network:v1 benchmarks/requests-network
python benchmarks/requests-network/harness.py -d /absolute/path/grading.json -p /absolute/path/predictions.jsonl -id isolated-check --max_workers 2 --timeout 300 --report_dir /absolute/path/results
```

Image preparation downloads fixed dependencies over HTTPS. Configure any
machine-specific proxy in that command's environment or Docker build arguments;
the project does not contain a host proxy address. Do not disable TLS checks.

## Preserved behavior and records

- All task repositories are restored to their exact upstream base commit before
  applying the prediction and the independent test patch.
- Requests' historical expression-string `pytest.raises` is implemented by
  executing that expression in the caller's scope inside modern `pytest.raises`.
  Missing or wrong exceptions still fail. Its compatibility semantics have unit
  tests in `tests/test_legacy_pytest_fixture.py`.
- The fixtures supply HTTPBin URLs and page content; they do not replace the
  Requests or Sphinx functions being repaired.
- The default Requests test deadline is 30 seconds per test; the harness has a
  separate case deadline. Timeouts are errors, never successful resolutions.
- ANSI escape codes are removed for the upstream parser, with original outputs
  retained under `raw-test-outputs/`. Individual reports and test logs remain in
  the harness output directory.

Before scoring generated patches, run the exact reference patch and a
behavior-preserving negative-control patch for every selected task. Both must
complete: the reference must resolve, and the negative control must remain
unresolved. Keep these controls outside Agent-visible workspaces. The November
18 development cohort passed both controls for all 20 tasks.
