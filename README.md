# PatchLab

PatchLab is an independent course project for comparing single-attempt and iterative Python repair. A model selects evidence to inspect and proposes exact source edits. PatchLab builds a diff from a frozen Git revision, optionally presents it for approval, and verifies it against a bug reproducer followed by regression tests.

See [the proposal technology plan](docs/proposal-technology-plan.md) for section-by-section recommendations and English wording for the proposal.

小组成员与 AI 工具请先阅读 [项目介绍与交接](HANDOFF.md)，其中列出当前能力、使用步骤、待办、限制和分工建议。

## Windows 一键启动

安装 Python 3.12+ 和 Git 后，双击项目目录中的 `start.cmd`。首次启动会创建项目自己的 `.venv`、安装 pytest，并提供三种选项：默认使用 DeepSeek 官方 V4.1 Flash（只需输入 DeepSeek 官方 API 密钥）；选择其他兼容服务（输入完整接口地址、模型名称和密钥）；或暂不配置先打开页面。若选择保存密钥，Windows 会以当前用户身份加密后保存在 `configs/.model-key`；配置和密钥文件都不会提交到 Git。后续双击即可启动并打开浏览器。启动窗口运行本地 Python 服务和 Agent 控制器；关闭启动窗口会停止服务。

DeepSeek 默认地址为 `https://api.deepseek.com/chat/completions`，模型名为 `deepseek-flash`，这是指向当前 Flash 版本的官方别名。默认设置关闭 DeepSeek thinking 模式，以适配目前的短输出上限和结构化动作；仍由 Agent 使用工具和测试反馈进行多步修复。该默认选项需要 DeepSeek 官方 API 密钥；HKU 或其他服务商的密钥应选“其他兼容服务”并使用其提供的地址和部署名。正式实验须记录官方别名实际对应的模型版本，别名可能随服务商更新。

首次安装需要能访问依赖来源。已有 `PATCHLAB_API_KEY` 环境变量优先于保存的密钥。更换模型可编辑 `configs/my-model.toml`；若其他服务商不支持 DeepSeek 的 thinking 参数，请删除 `thinking` 配置。更换已保存密钥可删除 `configs/.model-key` 后重新启动。也可以首次跳过模型设置先打开界面，但只有配置模型后才能对话或修复。

命令行也可运行 `./start.cmd`；若默认 8765 端口被占用，可运行 `./start.cmd --port 8766`。

## macOS 启动

安装 Python 3.12+ 和 Git，打开“终端”进入项目目录，首次运行：

```bash
chmod +x start.command
./start.command
```

之后可以双击 `start.command`。也可以直接在终端运行 `bash start.command`（无需修改执行权限），或运行 `bash start.command --port 8766` 指定端口。首次启动会创建 `.venv`、安装依赖并引导配置模型。输入密钥后可选择保存到 `configs/.macos-keys.json`，下次自动读取；选择不保存则只在本次运行中使用，也可通过环境变量提供。该文件在 macOS 上以仅当前用户可读写的权限创建，已被 Git 忽略，但**内容是明文，并非加密**；不要分享或提交这个文件。关闭启动终端会停止本地服务。

Windows 和 macOS 的 `.venv` 不能互相复制，请在各自电脑上分别安装。macOS 启动器经过模拟平台测试，尚未在真实 Mac 上验证；模型服务和目标项目的执行环境也需分别联调。

## 本地工作台

完成下面的 Python 环境安装和模型配置后，在当前 PowerShell 窗口设置好密钥，运行：

```powershell
.\.venv\Scripts\python.exe -m patchlab web --model-config configs\my-model.toml
```

程序会打开本机浏览器；若没有自动打开，复制终端打印的完整地址。页面可进行普通对话，也可以选择「修复任务」，填写 Git 仓库、允许编辑的文件、定向测试和回归测试，然后发送缺陷描述。页面按步骤显示决策、检查和测试记录，并显示通过测试的补丁。当前页面自动验证候选补丁，不支持页面内人工审批；原仓库不会被修改。输入 Docker 镜像可以使用现有容器执行接口，否则必须明确选择信任本机测试。Docker 与真实模型仍需要在实际环境中联调验证。

修复任务现在提供两种设置：**简易模式**填写项目路径和问题描述，可选填写操作步骤或启动命令；Agent 检查当前 Python 文件并尝试生成独立的 pytest 复现测试。只有原代码出现断言失败后才会验证候选补丁。简易模式在本机临时副本执行模型生成的测试，仅适合信任的项目；启动命令只作为模型线索，不会自动执行。它目前不支持自动操作 GUI、安装目标项目依赖或执行任意启动命令。项目无需是 Git 仓库，当前未提交的文件也会被复制；隐藏文件、虚拟环境和 Git 元数据不会复制。如果没有现成回归测试，结果会明确标记验证范围有限。**专业模式**沿用 Git 版本、允许修改文件和测试范围等设置。

会话及完整事件保存在 `runs/sessions`，浏览器可在最近会话中切换。当未压缩对话超过 12 条或上下文超过约 16000 字符时，模型会把较早内容压缩为摘要，保留最近 6 条原始消息；后续请求使用摘要加新消息。摘要检查点和原始消息均写入会话日志；若压缩失败，本轮报告错误，原始记录不会删除。阈值按字符估算，不等同于模型 token 数；摘要可能遗漏细节。修复过程中较长的工具结果和失败记录也会被压缩成摘要，完整事件仍保留在运行日志中。

模型调用遇到限流、暂时性服务错误、连接错误或超时时，最多尝试 3 次并采用指数退避；不可重试错误直接报告。可能已经被服务端处理过的请求重试可能产生额外费用。暂时性文件读取失败也会有限重试；测试失败、超时或无效补丁会交给 Agent 分析，不会自动重复执行。日志可能包含源码、测试输出和对话，请按项目情况保管。服务仅监听本机；不要向他人分享终端显示的访问地址。

当前 `model_calls` 和 token 汇总主要统计决策请求，不包含所有摘要请求或失败重试，不能作为完整费用统计。正式实验前需补齐全请求用量与成本记录，并固定摘要阈值和重试策略。

## Offline demo

Requires Python 3.12+, Git, and pytest. From this directory, using PowerShell:

```powershell
python -m venv .venv
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
```

切换兼容模型时复制另一份配置并修改 URL、模型名和（必要时）密钥环境变量，运行时用 `--model-config configs/my-model.toml` 选择。`PATCHLAB_API_URL` 和 `PATCHLAB_MODEL` 若已设置，会覆盖文件中的 URL 和名称；不需要时用 `Remove-Item Env:PATCHLAB_API_URL,Env:PATCHLAB_MODEL -ErrorAction SilentlyContinue` 清除。仅设置这两个变量和 `PATCHLAB_API_KEY` 也可不使用配置文件。

接口要求兼容非流式 chat completions 的 `messages`、`max_tokens`、`temperature` 请求和 `choices[0].message.content` 响应，模型须能返回指定的 JSON 动作。不同供应商的私有认证方式、请求字段或响应格式可能需要另写适配器，不能保证只换 URL 即可使用。远程地址须使用 HTTPS；本地回环地址可用 HTTP。请求会发送问题描述、所读取的源码及测试输出。DeepSeek 已有一次 QuixBugs 本地修复验证，其他供应商及后续核心改动仍需联调。

```powershell
python -m patchlab run --model-config configs/my-model.toml --repo D:/path/to/target --revision HEAD `
  --issue "Reversed intervals should have zero duration." `
  --editable interval.py --target test_interval.py::test_empty --suite test_interval.py `
  --image target-test-image:local --mode feedback --output runs/interval
```

Repeat `--editable`, `--target`, or `--suite` to supply multiple entries. Choose an editable list from production source files before running the model; do not use a reference patch to select the list. PatchLab reads committed files from a Git archive and leaves the working tree untouched. The initial targeted test must fail with pytest exit code 1. Use a targeted test that reliably reproduces the defect.

The Docker runner expects a locally available Linux image that provides `python`, pytest, and project dependencies. It disables networking, mounts the candidate read-only, and bounds execution. It does not pull images. `--trusted-local` runs Python and tests directly on the host, and is only for trusted code such as the bundled demo. The proposal controller uses fixed call and per-completion output limits; recorded token usage may be unavailable for some providers.

For the bundled QuixBugs development cases, build the minimal test image once:

```powershell
docker build -f docker/quixbugs.Dockerfile -t patchlab-quixbugs:dev .
```

Then pass `--image patchlab-quixbugs:dev` instead of `--trusted-local`. The image contains only
Python 3.12, pytest 9.1.1, and an unprivileged runtime user. PatchLab still applies its network,
mount, capability, memory, CPU, process, and timeout restrictions for each test command. Formal
experiments should record the built image ID. This image intentionally does not contain Git or
target-project dependencies beyond pytest; repository snapshots are prepared by the host.

Run the opt-in container integration tests after building the image:

```powershell
$env:PATCHLAB_DOCKER_IMAGE = 'patchlab-quixbugs:dev'
python -m pytest tests/test_docker_integration.py
```

## Run artifacts and evaluation

- `events.jsonl`: model decisions, inspection evidence, test output, and termination.
- `result.json`: outcome, diagnosis on success, measured time, and available token usage.
- `candidate-N.patch`: reviewable proposals, including ones that did not pass verification.
- `final.patch`: generated only after the supplied targeted and regression tests both pass.

Local success means the supplied tests passed. Five QuixBugs development examples are included, but SWE-bench provisioning and independent held-out grading are not implemented. Docker and the latest live-provider workflow still need deployment verification. The comparison command groups recorded runs by model and condition; keep task sets and configuration matched when using it for an experiment.

## 小组分工与后续接口

- Agent 核心：`patchlab/decision.py` 处理模型请求与动作；`patchlab/experiment.py` 管理观察、决策、失败反馈和三种模式。
- 工具与执行：`patchlab/workbench.py` 是目前的基础版本，供负责工具的组员继续完善，包括 Docker 实机验证、更多仓库类型和测试执行方式。控制器使用 `inspect`、`prepare`、`stage` 和测试运行器的 `run` 返回结果。
- 数据集与评测：当前已有 5 个 QuixBugs 开发案例和简单结果汇总。更完整的基准接入、任务冻结、独立验收、批量实验与报告留待负责评测的组员完成。
