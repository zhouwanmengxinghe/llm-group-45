# PatchLab

PatchLab is an independent course project for comparing single-attempt and iterative Python repair. A model selects evidence to inspect and proposes exact source edits. PatchLab builds a diff from a frozen Git revision, optionally presents it for approval, and verifies it against a bug reproducer followed by regression tests.

See [the proposal technology plan](docs/proposal-technology-plan.md) for section-by-section recommendations and English wording for the proposal.

## Offline demo

Requires Python 3.12+, Git, and pytest. From this directory, using PowerShell:

```powershell
python -m venv .venv
$env:HTTP_PROXY = $env:HTTPS_PROXY = 'http://127.0.0.1:7890'
$env:NO_PROXY = 'localhost,127.0.0.1,::1'
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m patchlab demo --trusted-local --mode feedback --output runs/demo
```

The scripted model's first proposal passes the targeted test and fails the regression test. The second proposal uses that evidence and passes both. Try `--mode single --output runs/single` to see the baseline stop after the first failure (exit code 1), or `--mode memory --output runs/memory` to exercise the history mode. Each output directory must be new. `--approve` presents each candidate and waits for a decision before testing.

```powershell
.\.venv\Scripts\python.exe -m patchlab summarize runs/single/result.json runs/demo/result.json
.\.venv\Scripts\python.exe -m pytest
```

## Repair a committed Python revision

### 模型接入与切换

复制 `configs/model.example.toml` 为一个新文件，例如 `configs/my-model.toml`。填写服务商提供的**完整 chat completions URL** 和模型或部署名。`api_key_env` 是密钥所在环境变量的名称，不是密钥本身。以下在 PowerShell 中执行：

```powershell
Copy-Item configs/model.example.toml configs/my-model.toml
# 编辑 configs/my-model.toml，填写 url 和 name
$env:PATCHLAB_API_KEY = '在此填入你的密钥'
$env:HTTP_PROXY = $env:HTTPS_PROXY = 'http://127.0.0.1:7890'
$env:NO_PROXY = 'localhost,127.0.0.1,::1'
```

切换兼容模型时复制另一份配置并修改 URL、模型名和（必要时）密钥环境变量，运行时用 `--model-config configs/my-model.toml` 选择。`PATCHLAB_API_URL` 和 `PATCHLAB_MODEL` 若已设置，会覆盖文件中的 URL 和名称；不需要时用 `Remove-Item Env:PATCHLAB_API_URL,Env:PATCHLAB_MODEL -ErrorAction SilentlyContinue` 清除。仅设置这两个变量和 `PATCHLAB_API_KEY` 也可不使用配置文件。

接口要求兼容非流式 chat completions 的 `messages`、`max_tokens`、`temperature` 请求和 `choices[0].message.content` 响应，模型须能返回指定的 JSON 动作。不同供应商的私有认证方式、请求字段或响应格式可能需要另写适配器，不能保证只换 URL 即可使用。远程地址须使用 HTTPS；本地回环地址可用 HTTP。请求会发送问题描述、所读取的源码及测试输出。当前未接入或验证任何真实供应商。

```powershell
python -m patchlab run --model-config configs/my-model.toml --repo D:/path/to/target --revision HEAD `
  --issue "Reversed intervals should have zero duration." `
  --editable interval.py --target test_interval.py::test_empty --suite test_interval.py `
  --image target-test-image:local --mode feedback --output runs/interval
```

Repeat `--editable`, `--target`, or `--suite` to supply multiple entries. Choose an editable list from production source files before running the model; do not use a reference patch to select the list. PatchLab reads committed files from a Git archive and leaves the working tree untouched. The initial targeted test must fail with pytest exit code 1. Use a targeted test that reliably reproduces the defect.

The Docker runner expects a locally available Linux image that provides `python`, pytest, and project dependencies. It disables networking, mounts the candidate read-only, and bounds execution. It does not pull images. `--trusted-local` runs Python and tests directly on the host, and is only for trusted code such as the bundled demo. The proposal controller uses fixed call and per-completion output limits; recorded token usage may be unavailable for some providers.

## Run artifacts and evaluation

- `events.jsonl`: model decisions, inspection evidence, test output, and termination.
- `result.json`: outcome, diagnosis on success, measured time, and available token usage.
- `candidate-N.patch`: reviewable proposals, including ones that did not pass verification.
- `final.patch`: generated only after the supplied targeted and regression tests both pass.

Local success means the supplied tests passed. The MVP does not prepare QuixBugs, provision SWE-bench environments, or independently grade held-out tests. Docker and the live provider still need deployment verification. The comparison command groups recorded runs by model and condition; keep task sets and configuration matched when using it for an experiment.

## 小组分工与后续接口

- Agent 核心：`patchlab/decision.py` 处理模型请求与动作；`patchlab/experiment.py` 管理观察、决策、失败反馈和三种模式。
- 工具与执行：`patchlab/workbench.py` 是目前的基础版本，供负责工具的组员继续完善，包括 Docker 实机验证、更多仓库类型和测试执行方式。控制器使用 `inspect`、`prepare`、`stage` 和测试运行器的 `run` 返回结果。
- 数据集与评测：当前只有离线示例和简单结果汇总。基准数据接入、任务冻结、独立验收、批量实验与报告留待负责评测的组员完成。
