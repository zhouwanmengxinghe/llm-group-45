ARG BASE_IMAGE=swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-3069:latest
FROM ${BASE_IMAGE}
USER root
COPY wheels /opt/patchlab-tests/wheels
# The historical project uses mode.use_inf_as_null, removed in pandas 2.0.
RUN /opt/miniconda3/envs/testbed/bin/python -m pip install --no-index --no-deps --find-links=/opt/patchlab-tests/wheels pandas==1.5.3 \
    && /opt/miniconda3/envs/testbed/bin/python -c "import numpy,pandas; print(numpy.__version__,pandas.__version__); assert pandas.get_option('mode.use_inf_as_null') is False" \
    && /opt/miniconda3/envs/testbed/bin/python -m pip freeze > /opt/patchlab-tests/installed.txt
