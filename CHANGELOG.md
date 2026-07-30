# 更新日志

## v3.0.1 — 2026-07-31

### 可复现构建

- ZIP 构建改为固定文件顺序、路径格式与时间戳；相同源码在同一受支持运行环境中连续构建时，五个安装包保持逐字节一致。
- 构建回归现在自动执行两轮打包并比较全部 SHA256，不再只检查单轮包内容。
- 安装包仍按 `skills/*/SKILL.md` 动态枚举，继续排除缓存、临时文件、开发测试与重复嵌套目录。

### 仓库展示与治理

- 新增 `skills/README.md`，提供四个平级 Skill 的简明目录、分轨、精确路径与安装入口。
- 新增 `docs/superpowers/README.md`，说明设计、计划与评测证据的用途，避免与运行时文件混淆。
- README 中英文版突出稳定版本、CI、Source Available 许可与正式下载入口；工作流明确展示可复现构建检查。
- GitHub Actions 升级到 Node.js 24 运行时对应的 `actions/checkout@v6` 与 `actions/setup-python@v6`，清除旧 Node.js 20 Action 警告。
- 扩展 Windows、macOS 与 Python 本地残留忽略规则；四个 Skill 的业务能力、许可边界和 `sg-aibp` 规划状态均未改变。

## v3.0.0 — 2026-07-30

### AIBP 正式版本

- 总品牌更新为 AIBP（AI Business Partner），采用 `core`、`commerce`、`tooling` 三条逻辑分轨；四个 Skill 仍平铺在 `skills/<slug>`。
- 现有仓库改名为 `sgskills/aibp`，保留完整 Git 历史与 `v1.4.0` tag；正式版使用 `v3.0.0` Release 分发。
- 复制导入 `sg-tmads-report` 与 `sg-skill-optimizer`，两个独立源目录保留；optimizer 仅迁入单层有效内容。

### Skill 优化

- `sg-ceo-vision` 统一中文名称为“CEO视角”，从电商限定扩展为跨行业商业方向、资源与年度路径判断，并新增非电商与相邻任务边界案例。
- `sg-mece` 统一中文名称为“电商经营结构化拆解”，补齐 CEO/专业诊断边界、轻量模式、停止追问、失败恢复与工具不可用案例。
- `sg-tmads-report` 增加字段级数值校验、原始字段允许名单、费率 `scope` 闸门、原子写入与可执行回归。
- `sg-skill-optimizer` 统一内部版本为 `2.5.0`，明确普通业务优化不触发 tooling，并保证安装包中的 runner 同时携带 6 个 Golden fixtures。

### 工程与构建

- validator 与 build 改为动态枚举 `skills/*/SKILL.md`，支持 YAML block description，并检查“功能定义在前、触发信息在后”。
- validator 自测增加第五个合规 Skill 绿测，以及缺 `SKILL.md`、嵌套目录和坏 frontmatter 红测。
- 构建输出四个单包、`aibp-3.0.0.zip` 与五条 SHA256；GitHub Release 同时提供五个 ZIP 与 `SHA256SUMS.txt`。

## v2.0.0 — 2026-07-29

### 破坏性迁移

- `sgs-mece` 已迁移为 `sg-mece`，不保留旧名称兼容壳。
- 请把显式调用与本地文件夹名更新为 `$sg-mece`；已有 `v1.4.0` tag 保留，仍可作为旧名称版本的回退点。

### 新增

- 新增 `sg-ceo-vision` / CEO Vision：独立运行的商业机会识别与年度规划 Skill，内置证据、可逆性和 HTML 报告边界。
- 为 `sg-ceo-vision` 增加六类评测：触发、反触发、证据不足、不可逆决策、独立性与离线 HTML 输出。
- 为 `sg-ceo-vision` 增加轻量知识产权与品牌资产检查点：核验权属/授权、识别长期资产价值，并对受影响的不可逆动作执行局部 STOP。

### 验证与打包

- 校验器现要求仓库仅有 `sg-mece` 与 `sg-ceo-vision`，并校验元数据、引用、资产、评测覆盖和旧前缀清理。
- 构建与测试现要求 v2.0.0 的两个独立安装包和一个完整套装包。

## v1.4.0 — 2026-07-29

- 首次仓库化发布 `sgs-mece`，建立元数据、评测、PowerShell 校验和双包构建基础。

## v1.3.1 — 2026-07-27

- 修正 README 作者信息与真实贡献者署名。

## v1.3.0 — 2026-07-27

- 增加认知负担、决策就绪条件与追问退出规则。

## v1.2.0 — 2026-07-27

- 增加不可逆决策检查点和可逆试验要求。

## v1.1.0 — 2026-07-27

- 增加动态追问、信息状态门槛和无可靠来源阈值保护。

## v1.0.0 — 2026-07-26

- 创建首版结构化拆解流程、候选框架和追问问题库。
