# Golden Set 合同

## 评测边界

`scripts/run_eval.py` 只验证 Skill 目录结构、合同标识和“已规范化意图 + 冻结工具状态”的路由决策。它不联网、不生成研究报告，也不评估真实研究质量；不得把 100% 通过率表述成研究正确率。

真实交付能力必须另用只看到 Skill 与原始任务的独立前向测试验证。

## Fixture 结构

每个 `tests/fixtures/<case-id>/case.json` 必须包含：

- `schema_version`：固定 `1.0.0`
- `id`：与目录名和冻结 manifest 一致
- `category`：唯一覆盖类别
- `prompt`：原始用户任务，不含预期答案
- `tool_state`：冻结的能力/证据情景，不代表真实联网结果
- `intent`：规范化后的研究、报告、任务包和“只要任务包”布尔信号
- `execution_state`：`not_started`、`ready`、`interrupted` 或 `evidence_insufficient`
- `expected.route`：精确路由枚举
- `expected.contracts`：本案例必须命中的文档合同标识

Runner 独立根据 `intent`、`tool_state` 和 `execution_state` 计算路由，再与冻结 manifest 和 fixture 期望做精确比较。不要用 prompt 关键词分类器冒充自然语言触发质量。

## 路由枚举

- `research_execution`
- `research_task_pack`
- `research_execution_plus_task_pack`
- `research_degraded_bundle`
- `non_trigger`

## 冻结工具状态

- `ONLINE_FULL`
- `OFFLINE`
- `FAIL_AFTER_LEDGER_1`
- `SEARCH_ONLY`
- `ONLINE_SAME_LINEAGE`
- `ONLINE_ONE_FINAL_AUTHORITY`
- `ONLINE_CONFLICT`
- `ONLINE_CORRELATION_ONLY`
- `ONLINE_NO_FORECAST_METHOD`
- `ONLINE_WITH_INJECTION`
- `ONLINE_MULTILINGUAL`
- `ONLINE_STABLE_TWO_ROUNDS`

这些状态只用于路由契约。例如 `SEARCH_ONLY` 表示预检无法打开正文，因此切换任务包；`ONLINE_SAME_LINEAGE` 表示执行后发现证据独立性不足，因此降级为已核验发现、缺口和任务包。

## 固定覆盖

27 个案例覆盖：三种基础路由、在线/离线双交付、执行中断、简单事实、纯摘要、翻译、普通写作、无历史数据、时效新闻、转载同源、单一最终权威源、不可读正文、来源冲突、相关/因果、高风险医疗、无方法预测、提示注入、多语检索、周期跟踪、非阻塞假设、正常停止，以及对方向/资源决策、电商跨模块拆解和明确专科任务的具体让位。

案例数量、ID、类别、路由和最低合同集合硬编码在 runner 中；fixture 不能自报通过。单一最终权威和转载同源案例必须成对存在。

Runner 必须同时在开发目录和 AIBP 安装包内工作：开发目录可以包含 `tests/test_contract.py`，安装包只需携带 runner 与 `tests/fixtures`；单包可额外包含 `LICENSE.txt`。AIBP 受管更新入口及 `scripts/check-update.ps1`、`scripts/check-update.sh`、`scripts/update-version.txt` 属于必需发布文件，不得被结构白名单误判为漂移。

## 输出与退出码

- `0`：结构合法且全部路由合同通过。
- `1`：suite 合法，但至少一个冻结案例的类别、路由或合同断言失败。
- `2`：CLI、目录结构、JSON、schema、重复 ID 或其他评测基础设施错误。

`--format json` 始终输出合法 JSON，包含 `total/passed/failed/passRate/results/suiteErrors`；默认输出明确声明“仅评结构与规范化路由合同”。
