FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m pip install --no-cache-dir \
        iniconfig==2.3.1 \
        packaging==26.3 \
        pluggy==1.7.0 \
        pygments==2.21.0 \
        pytest==9.1.1 \
    && useradd --create-home --uid 10001 patchlab

USER patchlab
WORKDIR /repo
ENTRYPOINT ["python"]
