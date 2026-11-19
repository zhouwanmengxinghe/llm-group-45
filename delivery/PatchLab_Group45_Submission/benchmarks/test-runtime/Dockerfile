# Build with a local wheelhouse prepared using requirements.lock.
ARG BASE_IMAGE=swebench/sweb.eval.x86_64.django_1776_django-13346:latest
FROM ${BASE_IMAGE}
USER root
COPY requirements.lock /opt/patchlab-tests/requirements.lock
COPY wheels /opt/patchlab-tests/wheels
RUN /opt/miniconda3/envs/testbed/bin/python -m pip install --no-index --find-links=/opt/patchlab-tests/wheels pytest==6.2.5 \
    && /opt/miniconda3/envs/testbed/bin/python -m pytest --version \
    && /opt/miniconda3/envs/testbed/bin/python -m pip freeze > /opt/patchlab-tests/installed.txt
