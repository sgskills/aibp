# SKILL.patch.md —— sg-skill-optimizer 变更记录

> 只记录已经验证、可回滚的本 Skill 变更。新问题先进入测试，再进入实现。

## [2026-07-30] v2.5.0 规则适用性与叙事契约

- `description` 改为“一句话定位 + 触发方式 + 边界 + 英文等价”，正文开场补齐角色、任务、交付、边界与前提。
- 反触发明确限定普通广告、商品、内容和经营“优化”不是 tooling 请求；只有目标本身是 Skill/Agent 才触发。
- 新增 `references/rule_applicability_review.md`：先区分元 Skill 与业务 Skill，再决定静态规则是否适用，避免将通用清单误套为业务缺陷。
- 静态检查改为识别多行编号步骤、任意交付模板、`output-contract.md` 格式规则和“独立于”声明；新增针对天猫报表业务 Skill 的回归断言。

## [2026-07-30] v2.4 叙事与路由规范
- 新增 `references/skill_narrative_standard.md`：定义 frontmatter 一句话定位、正文“角色/任务/交付/边界/前提”开场契约，以及不依赖其他 Skill 的安全收口。
- 主流程要求新建或改造 Skill 时先应用该规范，并在诊断中检查首句、开场、反触发和导航证据。
- 新增回归测试，确保规范文件存在且主流程直接引用；不引入外部品牌、命令、依赖或默认路由。

## [2026-07-30] v2.3 固定请求模式
- 将 P1、P2、P3 收敛为 `PLAN_ONLY`、`READ_ONLY`、`CONFIRMED_EXECUTION` 三个互斥模式，并写明每种模式的允许动作与固定交付。
- P1 明确写入为 0；P2 禁止因体检创建备份、日志或 fixture；P3 缺少可追溯目标、允许路径或验收命令时必须 STOP，不得写入。
- 新增回归测试验证模式名、只读边界、确认计划追溯和写入清单要求；SKILL.md 仍低于 300 行。

## [2026-07-30] v2.2 解析与镜像审计修正
- 块标量解析读取 `description: |` 与 `description: >` 的缩进正文，不再把标量符号当作描述内容。
- 镜像去重只保留一个硬链接文件，并跳过同名且 description 完全一致的目录副本；不同路径、不同名称的 C/D 仍是冲突候选。
- 新增 5 个独立测试覆盖块、折叠、硬链接、镜像和 C/D；原 Golden Set 保持 6/6。
- 回滚：从 `sg-skill-optimizer.backup-20260730-153807` 恢复 `scripts/common.py`，并移除新增测试文件与 `tests/fixtures/07-block-scalar/`。

## [2026-07-30] v2.1 严格评审修正版

- **安全执行**：目标 runner 默认不执行；必须先检查并确认，再显式提供 `--allow-target-code`；增加 30 秒超时和结果一致性校验；不一致时清空可信 `passRate`，仅保留 `reportedPassRate` 供取证。
- **解析正确性**：拒绝明显非法的 YAML 标量，例如未闭合列表或引号。
- **扫描隔离**：环境级 Skill 审计排除 `tests/fixtures`、缓存、依赖、版本控制和虚拟环境目录。
- **分数解释**：新增 `scoreScope` 与 `scoreCoverage`；N/A 不扣适用项分，但会降低覆盖率和置信度。
- **资源一致性**：报告模板权重与运行时统一；默认文本报告包含系统化待确认执行计划。
- **发布清理**：示例、方法论和变更记录改为通用、自包含内容，不携带旧业务素材或未确认来源说明。
- **回滚**：恢复本目录的 v2.0 快照，或删除本目录继续使用原 `skill-optimizer`；原目录始终保持不变。

## [2026-07-30] v2.0 独立评测版

- 目录名、Skill name 统一为 `sg-skill-optimizer`。
- 核心能力完全自包含，不依赖 Darwin 或其他 Skill。
- 静态分、回归状态、真实表现与置信度分开报告。
- 跨 Skill 审计在没有 `skills-root` 时为 `N/A`，不作为缺陷。
- 新增 6 个可执行 fixture、机器断言 runner 和单元回归。
- 新增显式 `🔴 CHECKPOINT · 🛑 STOP`、三段式失败矩阵和三档输出。
- 原 `skill-optimizer` 保持不变，可独立回滚。
