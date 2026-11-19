ARG BASE_IMAGE=swebench/sweb.eval.x86_64.psf_1776_requests-2317:latest
FROM ${BASE_IMAGE}
USER root
COPY requirements.lock prepare.sh server.py legacy_pytest.py /opt/patchlab-network/
RUN /opt/miniconda3/envs/testbed/bin/python -m pip install \
    --index-url https://pypi.org/simple \
    --cert /opt/miniconda3/envs/testbed/ssl/cert.pem \
    --timeout 120 --retries 5 -r /opt/patchlab-network/requirements.lock
RUN sed -i 's|http://|https://|g' /etc/apt/sources.list \
    && apt-get -o Acquire::Languages=none update \
    && apt-get install -y --no-install-recommends iptables \
    && bash /opt/patchlab-network/prepare.sh
ENTRYPOINT ["/usr/bin/env"]
