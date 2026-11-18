# PatchLab SWE-bench Verified 正式实验报告

## 1. 实验目的

本实验评估 PatchLab 在真实开源项目缺陷上的自动修复能力，并比较三种运行模式：

- `single`：只提交一个候选补丁；
- `feedback`：允许根据候选补丁的公开测试反馈继续修改；
- `memory`：在 `feedback` 基础上保留并压缩多轮历史证据。

核心问题是：在相同题目、模型、调用上限和评分环境下，引入测试反馈与历史记忆后，官方 SWE-bench 修复成功率是否提高。

## 2. 实验设计

### 2.1 数据与题目

实验使用 SWE-bench Verified 的 `test` 集。题目在任何正式模型调用之前冻结，并且失败后不替换。10 道题来自三个仓库：

- Django：4 道；
- SymPy：3 道；
- Sphinx：3 道。

冻结版本如下：

- SWE-bench Verified 数据集 revision：`78f471bf655a3137b2e8a75af1501690ec009ec3`；
- SWE-bench 任务仓库 revision：`3d07b464b7b311a0cbfb5ed5b2d8a3b96f84a33d`；
- 官方评分工具 revision：`02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`；
- PatchLab 行为实现 revision：`05959ae33bd496125aeb334c5625a368c6a0b24c`。

开发阶段已经使用过的 SWE-bench 题目没有进入本次正式样本。

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

所有题目串行执行。生成阶段只向 Agent 提供公开问题描述、允许读取的源码和预先选择的公开回归测试，不提供 `gold.patch`、`test.patch`、`tests.json`、hints 或隐藏测试输出。

### 2.3 主要评价指标

主要指标是官方 SWE-bench 隐藏测试给出的 `resolved` 比例，分母固定为每种模式的全部 10 道题。

没有生成合法补丁的题目计为 `empty_patch`，生成补丁但未通过官方测试的题目计为 `unresolved`。公开测试通过只代表 `candidate_ready`，不能代替官方成功结果。

## 3. 主要结果

| 模式 | Resolved | Unresolved | Empty patch | 官方成功率 | 95% Wilson 区间 |
| --- | ---: | ---: | ---: | ---: | ---: |
| single | 4 | 1 | 5 | 40% | 16.8%–68.7% |
| feedback | 4 | 1 | 5 | 40% | 16.8%–68.7% |
| memory | **5** | **0** | 5 | **50%** | 23.7%–76.3% |

三种模式都在 10 道题中的 5 道生成了可交给官方评分器的补丁。在这些非空补丁中：

- `single`：4/5 通过隐藏测试；
- `feedback`：4/5 通过隐藏测试；
- `memory`：5/5 通过隐藏测试。

条件化的“非空补丁通过率”不能替代主要指标，因为生成不出补丁本身也是系统失败。正式结论仍以全部 10 道题为分母。

## 4. 逐题对照

符号说明：`✓` 为 resolved，`✗` 为 unresolved，`—` 为 empty patch。

| 仓库 | 题目 | single | feedback | memory |
| --- | --- | :---: | :---: | :---: |
| Django | `django__django-12419` | — | ✓ | ✓ |
| Django | `django__django-14580` | — | — | — |
| Django | `django__django-13569` | — | ✗ | — |
| Django | `django__django-12155` | ✓ | ✓ | ✓ |
| SymPy | `sympy__sympy-21596` | — | — | — |
| SymPy | `sympy__sympy-16450` | ✓ | ✓ | ✓ |
| SymPy | `sympy__sympy-15349` | — | — | — |
| Sphinx | `sphinx-doc__sphinx-8595` | ✓ | ✓ | ✓ |
| Sphinx | `sphinx-doc__sphinx-7454` | ✗ | — | — |
| Sphinx | `sphinx-doc__sphinx-8120` | ✓ | — | ✓ |

这个对照表显示，总分相同不代表行为相同：

- `feedback` 修复了 `single` 没有生成补丁的 `django__django-12419`；
- 但 `feedback` 没有生成 `single` 已成功修复的 `sphinx-doc__sphinx-8120` 补丁；
- `memory` 同时修复了这两道题，因此总分比另外两种模式多 1 题。

## 5. 按仓库统计

| 仓库 | 题数 | single | feedback | memory |
| --- | ---: | ---: | ---: | ---: |
| Django | 4 | 1/4 | 2/4 | 2/4 |
| SymPy | 3 | 1/3 | 1/3 | 1/3 |
| Sphinx | 3 | 2/3 | 1/3 | 2/3 |

样本量太小，按仓库结果只能用于描述，不能据此判断某种模式对特定项目一定更有效。

## 6. 生成过程与资源消耗

| 模式 | Provider 请求数 | 已记录 provider tokens | Token 记录完整的运行 | 模型调用中位数 | 完整运行的 token 中位数 | 生成耗时合计 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| single | 73 | 191,270 | 9/10 | 4.0 | 9,227 | 341.563 秒 |
| feedback | 99 | 292,029 | 10/10 | 8.5 | 20,662 | 368.866 秒 |
| memory | 111 | 331,717 | 10/10 | 12.5 | 40,186 | 383.679 秒 |
| 合计 | 283 | 815,016 | 29/30 | — | — | 1,094.108 秒 |

`single` 有 1 次运行的 provider usage 不完整，因此 191,270 和总计 815,016 都应视为已记录值，而不是严格的完整 token 总量。

相较于 `single`，`memory` 的成功数从 4 增加到 5，但已记录 tokens 从 191,270 增加到 331,717。由于 `single` 的 token 总量不完整，不能据此计算精确成本增幅。实验也没有保存足够细的输入/输出 token 分类，不能仅凭总 token 准确换算 API 费用。

三种模式的 `recovered_after_failed_candidate` 都是 0。这意味着本批次没有观察到“公开测试失败后靠下一候选恢复成功”的案例；不同模式的得分差异主要来自它们是否在限制内生成了候选补丁以及最终补丁内容，而不是已测得的失败候选恢复能力。

## 7. 统计解释

这是同一组 10 道题上的配对实验，因此对模式间的 resolved 状态使用双侧精确 McNemar 检验：

- `single` 与 `feedback`：各自在 1 道题上独占成功，`p = 1.0`；
- `single` 与 `memory`：`memory` 独占成功 1 道，`p = 1.0`；
- `feedback` 与 `memory`：`memory` 独占成功 1 道，`p = 1.0`。

`memory` 的点估计最高，但 10 道题只产生 1 个成功案例的差距，置信区间高度重叠，无法证明差异具有统计显著性。因此合适的结论是：

> 在本次 10 题正式样本中，memory 取得最高观察成功率 50%，single 和 feedback 均为 40%；当前样本不足以证明 memory 稳定优于另外两种模式。

## 8. 失败与审计记录

- 正式分析使用完整的 `formal10-run-03`；
- `formal10-run-01` 在模型 API 调用前被中断，不属于结果；
- `formal10-run-02` 暴露了摘要请求错误使用 JSON response format 的基础设施问题，因此被排除；
- 修复后，30 次运行全部在同一实现 revision 下从头执行为 `formal10-run-03`；
- `feedback` 的 `sphinx-doc__sphinx-7454` 出现 1 次执行错误：`Context summary was incomplete; original context was retained.`；该结果按预先规则保留并计为空补丁，没有单独重跑或替换题目；
- 官方评分阶段三种模式均无 infrastructure failure、ambiguous failure 或评分 error；
- 官方评分结束后没有残留运行中的 Docker 容器；
- 10 个官方镜像被保留，以便复核，不影响成绩。

## 9. 有效性限制

1. 每种模式只有 10 道题，统计功效很低；
2. 每道题每种模式只运行 1 次，无法估计模型服务端随机性；
3. 三个仓库的题目数不同，不能代表整个 SWE-bench Verified；
4. 可编辑源码范围和公开回归测试由实验准备阶段选择，可能影响 Agent 搜索空间；
5. Apple Silicon 通过 amd64 兼容层运行官方镜像，影响耗时，但三种模式使用相同环境；
6. 一个 `single` 运行的 token usage 不完整，资源统计存在下界偏差；
7. 本批次没有出现失败候选后恢复成功的案例，尚不能直接验证反馈恢复机制的效果。

## 10. 可复现产物

仓库内保存以下不含密钥的实验定义：

- `benchmarks/swebench-formal10-selection.json`：题目选择规则；
- `benchmarks/swebench-formal10-lock.json`：冻结题目与版本；
- `benchmarks/swebench-formal10-experiment.json`：模型、上限和解释规则。

模型原始输出、补丁、运行事件、官方预测文件和大型评分日志按照项目约束保存在仓库外，不提交到 Git。正式批次的汇总入口为 `formal10-run-03/runs.csv` 和 `formal10-run-03/summary.json`，三份官方评分报告位于该批次的 `official-eval/logs/evaluation/` 下。

## 11. 结论

PatchLab 已经在冻结的 10 道 SWE-bench Verified 题目上完成三种模式共 30 次独立生成，并通过官方隐藏测试评分形成闭环。`memory` 以 5/10 获得本批次最高成功率，`single` 和 `feedback` 均为 4/10。官方评分过程没有基础设施故障。

本实验说明 PatchLab 已具备可重复的真实项目修复与官方评分能力，也给出了 memory 可能改善成功率的初步信号；但由于样本量小、无重复运行且差距仅 1 题，下一批实验应继续使用预先冻结的新题目，而不把本批次结果解释为确定性的模式优劣结论。
