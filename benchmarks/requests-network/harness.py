"""Run the upstream harness with isolated, offline runtime fixtures.

This does not change test files, patches, assertions, or grading rules.
Dependency installation uses the preinstalled build environment without PyPI.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import runpy
import sys
import tarfile

from docker.models.containers import Container, ContainerCollection
from offline_setup import offline_setup


def plain_output(text):
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


def copy_helpers(container, directory, names):
    result = container.exec_run(["mkdir", "-p", directory], user="root")
    if result.exit_code:
        raise RuntimeError("Cannot create isolated fixture directory")
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as stream:
        for name in names:
            stream.add(str(Path(__file__).resolve().parent / name), arcname=name)
    if not container.put_archive(directory, archive.getvalue()):
        raise RuntimeError("Cannot install isolated fixture helpers")


def install(image, metadata=(), image2931="patchlab-requests2931-network:v1"):
    create = ContainerCollection.create
    start = Container.start
    list_containers = ContainerCollection.list

    def concurrent_inventory(collection, *args, **kwargs):
        # Another isolated worker can remove a container between Docker's list
        # and inspect requests. Ignore only that disappearance in inventory;
        # errors from creating, running, or grading a case still propagate.
        kwargs.setdefault("ignore_removed", True)
        return list_containers(collection, *args, **kwargs)

    ContainerCollection.list = concurrent_inventory

    def fixture_create(collection, *args, **kwargs):
        requested = kwargs.get("image", args[0] if args else "")
        if isinstance(requested, str):
            for row in metadata:
                org, task = row["instance_id"].split("__", 1)
                if org + "_1776_" + task in requested:
                    kwargs["labels"] = {**kwargs.get("labels", {}),
                        "patchlab.base_commit": row["base_commit"],
                        "patchlab.instance_id": row["instance_id"]}
                    break
            if not any(x in requested for x in ("psf_1776_requests-2317", "psf_1776_requests-2931")):
                kwargs["network_mode"] = "none"
        if isinstance(requested, str) and any(x in requested for x in ("psf_1776_requests-2317", "psf_1776_requests-2931")):
            selected_image = image2931 if "requests-2931" in requested else image
            if args:
                args = (selected_image, *args[1:])
            else:
                kwargs["image"] = selected_image
            kwargs["labels"] = {**kwargs.get("labels", {}),
                                "patchlab.network-fixture": "requests-local-v2"}
            kwargs["cap_add"] = [*kwargs.get("cap_add", []), "NET_ADMIN"]
            kwargs["extra_hosts"] = {**kwargs.get("extra_hosts", {}),
                "httpbin.org": "127.0.0.1", "www.google.co.uk": "127.0.0.1",
                "fooobarbangbazbing.httpbin.org": "127.0.0.2"}
            kwargs["dns"] = ["127.0.0.1"]
            bundle = "/opt/miniconda3/envs/testbed/lib/python3.9/site-packages/certifi/cacert.pem"
            kwargs["environment"] = {
                "HTTPBIN_URL": "http://localhost/",
                "SSL_CERT_FILE": bundle, "REQUESTS_CA_BUNDLE": bundle,
                "PYTHONPATH": "/opt/patchlab-network",
                "PYTEST_PLUGINS": "legacy_pytest",
                "PYTEST_ADDOPTS": "-vv --durations=20 --timeout=30 --timeout-method=signal",
                "PYTHONUNBUFFERED": "1",
                "HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "",
                "http_proxy": "", "https_proxy": "", "all_proxy": "",
                "NO_PROXY": "localhost,127.0.0.1,::1",
                "no_proxy": "localhost,127.0.0.1,::1",
            }
        if isinstance(requested, str) and "sphinx-doc_1776_sphinx-8475" in requested:
            kwargs["labels"] = {**kwargs.get("labels", {}), "patchlab.web-fixture": "static-pages-v1"}
            kwargs["extra_hosts"] = {**kwargs.get("extra_hosts", {}), **{
                host: "127.0.0.1" for host in ("www.w3.org", "www.google.com", "www.sphinx-doc.org")}}
            kwargs["dns"] = ["127.0.0.1"]
            kwargs["environment"] = {
                "SSL_CERT_FILE": "/opt/patchlab-web/bundle.pem",
                "REQUESTS_CA_BUNDLE": "/opt/patchlab-web/bundle.pem",
                "HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "",
                "http_proxy": "", "https_proxy": "", "all_proxy": "",
                "NO_PROXY": "localhost,127.0.0.1,::1", "no_proxy": "localhost,127.0.0.1,::1",
                "PYTHONUNBUFFERED": "1", "NO_COLOR": "1", "PY_COLORS": "0",
                "PYTEST_ADDOPTS": "-rA -vv",
            }
        if isinstance(requested, str):
            for issue in ("3069", "3187"):
                if "mwaskom_1776_seaborn-" + issue in requested:
                    selected_image = "patchlab-seaborn" + issue + "-tests:v1"
                    if args:
                        args = (selected_image, *args[1:])
                    else:
                        kwargs["image"] = selected_image
                    break
        kwargs["environment"] = {**kwargs.get("environment", {}),
            "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_CONFIG_FILE": "/opt/patchlab-offline/pip.conf"}
        if kwargs.get("name"):
            # Separate evaluator invocations may reuse an upstream run ID.
            # Their output directories provide distinct deterministic namespaces.
            namespace = hashlib.sha256(str(Path.cwd().resolve()).encode()).hexdigest()[:10]
            kwargs["name"] += "." + namespace
        return create(collection, *args, **kwargs)

    def fixture_start(container, **kwargs):
        value = start(container, **kwargs)
        container.reload()
        labels = container.attrs.get("Config", {}).get("Labels") or {}
        copy_helpers(container, "/opt/patchlab-offline", ["pip.conf"])
        instance = labels.get("patchlab.instance_id", "")
        tools = []
        if instance.startswith("pytest-dev__pytest-"):
            tools = ["setuptools_scm==6.4.2", "tomli==2.0.1"]
        elif instance in ("astropy__astropy-14365", "astropy__astropy-14995"):
            tools = ["setuptools_scm==6.4.2", "tomli==2.0.1",
                     "extension-helpers==1.1.0", "Cython==0.29.34"]
        elif instance.startswith("mwaskom__seaborn-"):
            tools = ["flit_core==3.9.0"]
        if tools:
            wheels = Path(__file__).resolve().parent / "build-wheels"
            for row in json.loads((wheels / "SHA256.json").read_text(encoding="utf-8")):
                if hashlib.sha256((wheels / row["file"]).read_bytes()).hexdigest() != row["sha256"]:
                    raise RuntimeError("Offline build wheel checksum mismatch: " + row["file"])
            copy_helpers(container, "/opt/patchlab-offline", ["build-wheels"])
            result = container.exec_run([
                "/opt/miniconda3/envs/testbed/bin/python", "-m", "pip", "install",
                "--no-index", "--no-deps", "--find-links=/opt/patchlab-offline/build-wheels",
                *tools], user="root")
            if result.exit_code:
                raise RuntimeError("Offline build tools could not be installed: " +
                                   result.output.decode(errors="replace"))
        base = labels.get("patchlab.base_commit")
        if base:
            reset = container.exec_run(
                ["git", "-c", "safe.directory=/testbed", "-C", "/testbed", "reset", "--hard", base],
                user="root")
            if reset.exit_code:
                raise RuntimeError("Could not restore frozen base: " + reset.output.decode(errors="replace"))
        if labels.get("patchlab.network-fixture") == "requests-local-v2":
            python = "/opt/miniconda3/envs/testbed/bin/python"
            copy_helpers(container, "/opt/patchlab-network", ["legacy_pytest.py"])
            blocked = container.exec_run(
                ["/usr/sbin/iptables", "-A", "OUTPUT", "-d", "10.255.255.1", "-j", "DROP"],
                user="root")
            if blocked.exit_code:
                raise RuntimeError("Could not configure private timeout fixture: " + blocked.output.decode(errors="replace"))
            for rule in (["-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT"],
                         ["-P", "OUTPUT", "DROP"]):
                blocked = container.exec_run(["/usr/sbin/iptables", *rule], user="root")
                if blocked.exit_code:
                    raise RuntimeError("Could not isolate fixture egress")
            container.exec_run([python, "/opt/patchlab-network/server.py"],
                               detach=True, user="root")
            ready = """
import time,urllib.request
for attempt in range(100):
    try:
        assert urllib.request.urlopen('http://localhost/status/200',timeout=1).status==200
        assert urllib.request.urlopen('https://httpbin.org/status/200',timeout=1).status==200
        break
    except Exception:
        if attempt==99: raise
        time.sleep(.1)
"""
            result = container.exec_run([python, "-c", ready], user="root")
            if result.exit_code:
                raise RuntimeError("Local HTTPBin startup failed: " + result.output.decode(errors="replace"))
        if labels.get("patchlab.web-fixture") == "static-pages-v1":
            python = "/opt/miniconda3/envs/testbed/bin/python"
            copy_helpers(container, "/opt/patchlab-web", ["static_web.py", "prepare_web.py"])
            prepared = container.exec_run([python, "/opt/patchlab-web/prepare_web.py"], user="root")
            if prepared.exit_code:
                raise RuntimeError("Local web certificate setup failed: " + prepared.output.decode(errors="replace"))
            container.exec_run([python, "/opt/patchlab-web/static_web.py"], detach=True, user="root")
            ready = """
import time,urllib.request
for attempt in range(100):
    try:
        assert urllib.request.urlopen('https://www.w3.org/',timeout=1).status==200
        break
    except Exception:
        if attempt==99: raise
        time.sleep(.1)
"""
            result = container.exec_run([python, "-c", ready], user="root")
            if result.exit_code:
                raise RuntimeError("Local static web startup failed: " + result.output.decode(errors="replace"))
        return value

    ContainerCollection.create = fixture_create
    Container.start = fixture_start
    from swebench.harness import docker_utils
    execute = docker_utils.exec_run_with_timeout

    def normalized_execute(container, *args, **kwargs):
        # Upstream repeats package installation inside eval.sh. Explicit flags
        # avoid pip-version-dependent boolean configuration semantics.
        command = kwargs.get("cmd", args[0] if args else "")
        if "/eval.sh" in str(command):
            original = container.exec_run(["cat", "/eval.sh"], user="root")
            if original.exit_code:
                raise RuntimeError("Cannot read evaluation script for offline setup")
            script = original.output.decode("utf-8")
            adapted = offline_setup(script)
            archive_dir = Path("evaluation-setup")
            archive_dir.mkdir(exist_ok=True)
            (archive_dir / (container.name + ".original.sh")).write_text(script, encoding="utf-8")
            (archive_dir / (container.name + ".offline.sh")).write_text(adapted, encoding="utf-8")
            payload = adapted.encode("utf-8")
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode="w") as stream:
                entry = tarfile.TarInfo("eval.sh")
                entry.size = len(payload)
                entry.mode = 0o755
                stream.addfile(entry, io.BytesIO(payload))
            if not container.put_archive("/", archive.getvalue()):
                raise RuntimeError("Cannot install offline evaluation setup")
        text, timed_out, duration = execute(container, *args, **kwargs)
        archive = Path("raw-test-outputs")
        archive.mkdir(exist_ok=True)
        (archive / (container.name + ".txt")).write_text(text, encoding="utf-8")
        return plain_output(text), timed_out, duration

    docker_utils.exec_run_with_timeout = normalized_execute


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--fixture-image", default="patchlab-requests-network:v1")
    parser.add_argument("--fixture2931-image", default="patchlab-requests2931-network:v1")
    args, rest = parser.parse_known_args()
    metadata = []
    for flag in ("-d", "--dataset_name"):
        if flag in rest:
            dataset = Path(rest[rest.index(flag) + 1])
            if dataset.is_file():
                metadata = json.loads(dataset.read_text(encoding="utf-8"))
                if not isinstance(metadata, list):
                    raise ValueError("Expected a local dataset list")
            break
    install(args.fixture_image, metadata, args.fixture2931_image)
    sys.argv = ["swebench.harness.run_evaluation", *rest]
    runpy.run_module("swebench.harness.run_evaluation", run_name="__main__")
