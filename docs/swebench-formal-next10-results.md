# PatchLab SWE-bench Verified 第二批正式实验报告

## 1. 实验目的

本实验在第一批正式实验之后，使用一组预先冻结且不重复的新题目，继续评估 PatchLab 的三种运行模式：

- `single`：只提交一个候选补丁；
- `feedback`：允许根据公开测试反馈继续修改；
- `memory`：在 `feedback` 基础上保留并压缩多轮历史证据。

主要问题仍然是：在相同题目、模型、调用上限和评分环境下，反馈与记忆机制能否提高官方 SWE-bench 修复成功率。

## 2. 实验设计

### 2.1 数据与题目

实验使用 SWE-bench Verified 的 `test` 集。10 道题在正式模型调用前冻结，失败后不替换，并排除了开发阶段题目和第一批正式实验的全部题目：

- Django：4 道；
- SymPy：3 道；
- Sphinx：3 道。

冻结版本如下：

- SWE-bench Verified 数据集 revision：`78f471bf655a3137b2e8a75af1501690ec009ec3`；
- SWE-bench 任务仓库 revision：`3d07b464b7b311a0cbfb5ed5b2d8a3b96f84a33d`；
- 官方评分工具 revision：`02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`；
- PatchLab 行为实现 revision：`05959ae33bd496125aeb334c5625a368c6a0b24c`。

### 2.2 模型与运行参数

- 模型：DeepSeek 官方 API 的 `deepseek-flash`；
- thinking：关闭；
- JSON mode：开启，但仅用于结构化修复决策；
- temperature：0；
- 每次运行最多 16 个逻辑决策；
- `single` 最多 1 个候选补丁；
- `feedback` 和 `memory` 最多 5 个候选补丁；
- 单次模型响应上限：1200 tokens；
- 公开测试超时：600 秒；
- 官方隐藏测试超时：1800 秒；
- 官方评分 worker：1；
- 每种模式每道题运行 1 次，共 30 次运行。

所有题目串行执行。生成阶段不向 Agent 提供 `gold.patch`、`test.patch`、`tests.json`、hints 或隐藏测试输出。官方评价以全部 10 道题为固定分母；没有生成合法补丁的题目计为 `empty_patch`。

## 3. 主要结果

| 模式 | Resolved | Unresolved | Empty patch | 官方成功率 | 95% Wilson 区间 |
| --- | ---: | ---: | ---: | ---: | ---: |
| single | **6** | 2 | 2 | **60%** | 31.3%–83.2% |
| feedback | 4 | 0 | 6 | 40% | 16.8%–68.7% |
| memory | 5 | 0 | 5 | 50% | 23.7%–76.3% |

在非空补丁中：

- `single`：6/8 通过官方隐藏测试；
- `feedback`：4/4 通过官方隐藏测试；
- `memory`：5/5 通过官方隐藏测试。

条件化的非空补丁通过率不能替代主要指标，因为生成不出补丁本身也是系统失败。本批次中，`single` 生成补丁的覆盖率最高，因此总体成功率也最高。

## 4. 逐题对照

符号说明：`✓` 为 resolved，`✗` 为 unresolved，`—` 为 empty patch。

| 仓库 | 题目 | single | feedback | memory |
| --- | --- | :---: | :---: | :---: |
| Django | `django__django-16527` | ✓ | ✓ | ✓ |
| Django | `django__django-11265` | ✗ | — | — |
| Django | `django__django-15128` | ✗ | — | — |
| Django | `django__django-12209` | ✓ | ✓ | ✓ |
| SymPy | `sympy__sympy-22914` | ✓ | ✓ | ✓ |
| SymPy | `sympy__sympy-23824` | ✓ | — | ✓ |
| SymPy | `sympy__sympy-17139` | ✓ | ✓ | ✓ |
| Sphinx | `sphinx-doc__sphinx-8551` | ✓ | — | — |
| Sphinx | `sphinx-doc__sphinx-9591` | — | — | — |
| Sphinx | `sphinx-doc__sphinx-7985` | — | — | — |

`feedback` 成功的 4 道题和 `memory` 成功的 5 道题都包含在 `single` 的 6 道成功题中。本批次没有出现迭代模式独占成功的题目。

## 5. 按仓库统计

| 仓库 | 题数 | single | feedback | memory |
| --- | ---: | ---: | ---: | ---: |
| Django | 4 | 2/4 | 2/4 | 2/4 |
| SymPy | 3 | 3/3 | 2/3 | 3/3 |
| Sphinx | 3 | 1/3 | 0/3 | 0/3 |

样本量很小，按仓库结果只能用于描述，不能据此判断某种模式对特定项目一定更有效。

## 6. 生成过程与资源消耗

| 模式 | Provider 请求数 | 已记录 provider tokens | Token 记录完整的运行 | 模型调用中位数 | 完整运行的 token 中位数 | 生成耗时合计 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| single | 99 | 298,739 | 10/10 | 8.0 | 17,170 | 353.291 秒 |
| feedback | 111 | 360,198 | 10/10 | 8.5 | 32,904 | 388.140 秒 |
| memory | 106 | 318,859 | 9/10 | 8.5 | 28,963 | 376.570 秒 |
| 合计 | 316 | 977,796 | 29/30 | — | — | 1,118.001 秒 |

`memory` 有 1 次运行的 provider usage 不完整，因此其 token 总量和总计都应视为已记录下界，而不是严格的完整消耗。三种模式的 `recovered_after_failed_candidate` 均为 0；本批次仍未观察到公开测试失败后靠后续候选恢复成功的案例。

## 7. 统计解释

这是同一组题目上的配对实验。对 resolved 状态使用双侧精确 McNemar 检验：

- `single` 与 `feedback`：`single` 独占成功 2 道，`feedback` 独占成功 0 道，`p = 0.5`；
- `single` 与 `memory`：`single` 独占成功 1 道，`memory` 独占成功 0 道，`p = 1.0`；
- `feedback` 与 `memory`：`memory` 独占成功 1 道，`feedback` 独占成功 0 道，`p = 1.0`。

因此合适的单批次结论是：

> 在第二批 10 题中，single 的观察成功率最高，为 60%；memory 为 50%，feedback 为 40%。样本量不足以证明三种模式存在稳定的统计差异。

## 8. 与第一批合并观察

两批使用互不重复的题目、相同模型和相同主要运行限制。合并 20 道题后的描述性结果为：

| 模式 | 第一批 | 第二批 | 两批合计 |
| --- | ---: | ---: | ---: |
| single | 4/10 | 6/10 | **10/20（50%）** |
| feedback | 4/10 | 4/10 | 8/20（40%） |
| memory | 5/10 | 5/10 | **10/20（50%）** |

第一批中 `memory` 最高，第二批中 `single` 最高；合并后两者同为 50%。这说明单个 10 题批次的领先关系不稳定，也进一步支持继续扩大预先冻结样本，而不是根据某一批次下确定性结论。

## 9. 失败与审计记录

- 30 次生成运行全部完成并保留；
- 生成状态为 17 次 `candidate_ready`、8 次 `decision_limit`、5 次 `execution_error`；
- 17 份非空补丁全部送入官方评分；其余 13 次按预定规则保留为空补丁，不重跑、不换题；
- `single` 的 8 份非空补丁中有 2 份未通过隐藏测试；
- `feedback` 和 `memory` 的所有非空补丁均通过隐藏测试；
- 官方评分阶段没有 infrastructure failure、ambiguous failure 或评分 error；
- 官方评分结束后没有残留运行中的 Docker 容器。

## 10. 有效性限制

1. 每种模式只有 10 道题，统计功效很低；
2. 每道题每种模式只运行 1 次，无法估计服务端随机性；
3. 三个仓库的题目数不同，不能代表整个 SWE-bench Verified；
4. 可编辑源码范围和公开回归测试由实验准备阶段选择，可能影响 Agent 搜索空间；
5. Apple Silicon 通过 amd64 兼容层运行官方镜像，影响耗时，但三种模式使用相同环境；
6. 一个 `memory` 运行的 token usage 不完整，资源统计存在下界偏差；
7. 两批实验均未出现失败候选后恢复成功的案例，尚不能直接验证反馈恢复机制的效果。

## 11. 可复现产物

仓库内保存以下不含密钥的实验定义：

- `benchmarks/swebench-formal-next10-selection.json`：第二批题目选择规则；
- `benchmarks/swebench-formal-next10-lock.json`：冻结题目与版本；
- `benchmarks/swebench-formal-next10-experiment.json`：模型、上限和解释规则。

模型原始输出、补丁、事件记录、官方预测文件和大型评分日志保存在仓库外，不提交到 Git。正式批次的汇总入口为 `formal-next10-run-01/runs.csv` 和 `formal-next10-run-01/summary.json`，三份官方评分报告位于该批次的 `official-eval/logs/evaluation/` 下。

## 12. 结论

PatchLab 已在第二组冻结的 10 道 SWE-bench Verified 题目上完成三种模式共 30 次生成和官方隐藏测试评分。`single` 以 6/10 获得本批次最高成功率，`memory` 为 5/10，`feedback` 为 4/10；评分过程没有基础设施故障。

结合第一批后，`single` 和 `memory` 均为 10/20，`feedback` 为 8/20。现有结果证明了实验流程可以稳定复现，但还不能证明带反馈或记忆的迭代模式稳定优于单候选模式。后续实验应继续扩大预先冻结样本，并优先调查迭代模式较高的空补丁率。
