"""Offline adaptation of dependency setup, independent of Docker and grading."""
import re


def offline_setup(script):
    """Adapt installation commands only; leave test commands and patches intact."""
    return re.sub(r"^python -m pip install ",
        "python -m pip install --no-index --no-deps --no-build-isolation ",
        script, flags=re.MULTILINE)
