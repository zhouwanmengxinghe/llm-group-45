# Legacy Django pytest runtime

The original Django images use Python 3.6 and 3.8 and their native Django test
runner. They do not necessarily include pytest. Model-generated reproductions
need pytest as an additional test tool; the original source and public test
command remain unchanged.

Download the pure Python wheels specified in `requirements.lock` to a private
build context containing `requirements.lock` and `wheels/`. Then build offline:

```sh
python -m pip download --only-binary=:all: --python-version 3.6.13 --no-deps -r benchmarks/test-runtime/requirements.lock -d /absolute/path/build/wheels
docker build --network none --pull=false -f benchmarks/test-runtime/Dockerfile --build-arg BASE_IMAGE=swebench/sweb.eval.x86_64.django_1776_django-13346:latest -t patchlab-django13346-tests:v1 /absolute/path/build
```

Repeat with the 14792 base and output tag. Supply the resulting image in the task
manifest equally to all conditions. These are locally derived test environments,
not newly downloaded official images. Save base/result image IDs and wheel
SHA-256 values with the experiment configuration. Network proxy configuration
belongs to the local download command, never the project or the task manifest.

The lock specifies the offline wheelhouse. The installer preserves existing
compatible dependencies rather than downgrading unrelated Django/Selenium
requirements; the actual environment is recorded in
`/opt/patchlab-tests/installed.txt` inside each resulting image.

## Historical Seaborn

Both Seaborn tasks use pandas' historical `mode.use_inf_as_null` option, removed
in pandas 2.0. A healthy `seaborn.objects.Plot` can therefore fail before any
repair in the cached environment. Obtain the official pandas 1.5.3 cp39 Linux
wheel, verify its PyPI SHA-256, and put it in a separate build context's wheels
directory. Build each base offline with `seaborn.Dockerfile` and output tags
`patchlab-seaborn3069-tests:v1` and `patchlab-seaborn3187-tests:v1`.
The adapter uses these same environments for independent grading. Re-run both
positive and negative controls before scoring generated patches.
