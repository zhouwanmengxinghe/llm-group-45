# COMP7608B 提案技术栈与改写计划

项目名称：**PatchLab — A Test-Driven Autonomous Debugging and Software Repair Agent**

原提案的研究问题保留：在同一模型、任务与资源上限下，使用测试反馈修订候选补丁，能否提高可验证的修复成功率？技术栈围绕这一个问题展开。

| 提案位置 | 建议写法 | 当前状态 |
| --- | --- | --- |
| §4.1 控制流程 | Python 3.12+ 单进程状态机，模型逐次选择文件列表、文本搜索、按行读取、提出修复或停止；控制器决定何时测试和结束 | 已实现 |
| §4.2 模型 | 可配置的非流式 chat-completions HTTP 接口，模型输出结构化 JSON；正式实验前冻结部署、温度和调用上限 | 接口已实现，真实部署待验证 |
| §4.2 补丁 | 从指定 Git 提交提取只读基线；每次候选都从基线独立生成。模型提交精确源码替换，由宿主生成 unified diff，展示给人审阅 | 已实现 |
| §4.2 测试与边界 | pytest 定向复现与回归；正式运行用预构建 Linux Docker 镜像，禁网、只读挂载，限制 CPU、内存和进程数 | 本地闭环已验证；Docker 实机待验证 |
| §4.2 记录 | JSONL 保存决策、检查结果和测试事件；JSON 汇总结果；独立保存每次候选 diff 及最终通过的补丁 | 已实现 |
| §5.1 数据 | 小型本地缺陷演示与回归；QuixBugs 用于开发；拟冻结 30 个 SWE-bench Verified 仓库级任务，正式结果由独立验收得出 | 仅内置演示；基准准备与独立验收待完成 |
| §5.2 对照 | 单次修复、最近一次失败反馈、带历史的反馈；后两者最多 5 个候选。固定调用次数与单次生成上限，报告实际用量 | 已有三种运行模式，正式对照待跑 |

LoopSmith 的参考范围限于设计理念：使用工具查找故障、依据测试信号修订、补丁审批及事件记录。PatchLab 的代码、目录结构、配置、提示词和测试夹具均独立编写。开启审批后，先展示差异文件，审批通过才把编辑写入临时副本；目标仓库始终不被修改。

## 可直接替换提案 §4.2 的英文段落

> We will implement PatchLab as a single-process Python command-line application with an explicit repair controller. At each decision point, a configurable language-model endpoint returns one structured action: list Python files, search for a literal, inspect a line range, propose exact source replacements, or stop. The controller validates the action and builds a unified diff against a fixed Git revision. When approval is enabled, the controller displays the diagnosis and diff before materializing the candidate in a separate disposable workspace. The agent may edit only existing Python source files on an operator-defined allowlist.
>
> Verification first runs the supplied defect reproducer with pytest, then runs the regression suite if the reproducer passes. We will use prebuilt Linux Docker environments for repository tests, with disabled network access, read-only repository mounts, timeouts, and CPU, memory, and process limits. JSONL events will record model decisions, inspection results, candidate test outcomes, and available token usage. We will save candidate diffs, the verified diff when available, and a run summary separately. The implementation will use one repair controller and a small set of repository operations.

## 建议同步调整实验章节

- **补丁入口与研究边界：**编辑范围由人工按生产源码目录或清单统一预先设定，不使用参考修复的文件列表。模型仍需要在允许范围内自主定位。当前 MVP 只修改已有的、UTF-8/LF 的 Python 文件；新增文件、非 Python 修复和依赖变更都不在当前范围。
- **公平对照：**同一任务、Git 提交、可编辑范围、初始证据、测试环境、模型和调用上限。单次组只提交一个候选；反馈组保留最近一次失败；记忆组保留最多五轮失败摘要并阻止重复 diff。三组都禁用人工审批。调用预算一致，并报告各组实际 token 和时间；最终记忆组的差异同时包含“保留更多历史”和“去重”。
- **盲测与指标：**供 Agent 调试的定向测试和用于最终计分的测试分开。正式解决率来自独立验收；本地报告用“通过所提供的测试”表述。冻结样本与排除规则后再跑模型，失败题不得按结果剔除。报告正式解决率、回归情况、失败后恢复、耗时、模型调用和 token；只有记录了费率才估算 API 成本。
- **实施顺序：**完成本地闭环 → 验证容器与真实模型 → 用 QuixBugs 做小样本开发 → 冻结 SWE-bench 题单并跑正式验收。Java 与 Defects4J 继续作为扩展目标。
