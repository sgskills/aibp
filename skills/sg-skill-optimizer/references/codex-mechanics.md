# Codex 5 大独特机制 + 映射表

> 由 SKILL.md 按需加载。涉及 Codex 适配时读本文件。
> Codex Skill 遵循 open agent skills 标准，与多数 agent 平台同源；只需针对以下 5 个 Codex 独有机制适配。

---

## 机制 ① 8000 字符 / 2% 上下文预算 —— description 会被自动截断
- Codex 把所有 Skill 的初始列表限制在 ≈2% 上下文或 8000 字符；Skill 多时会**自动缩短 description，甚至省略某些 Skill**。
- **强制要求**：关键用例和触发词必须**前置**（front-load），后半段会被砍。
- description 写法：`第一句 = 何时用 + 核心触发词` → 然后才是边界和反触发。
- ✅ 动作：description 重写成「倒金字塔」——最重要触发场景放第一句。用 `scripts/audit_description.py` 检测是否超预算。

## 机制 ② 安装位置决定作用域
| 作用域 | 路径 | 用途 |
|--------|------|------|
| REPO | `$CWD/.agents/skills`、`$REPO_ROOT/.agents/skills` | 项目专属 |
| USER | `$HOME/.agents/skills` 或 `~/.codex/skills/` | 个人全局（全家桶放这） |
| ADMIN | `/etc/codex/skills` | 机器级共享 |
| SYSTEM | Codex 内置（skill-creator、plan） | 官方 |
- ✅ 动作：跨项目通用的 Skill → `~/.codex/skills/`；项目专属 → `.agents/skills`。

## 机制 ③ `agents/openai.yaml` —— Codex 独有元数据 + 触发开关
```yaml
interface:
  display_name: "用户可见名"
  short_description: "一句话用途"
policy:
  allow_implicit_invocation: true   # false = 只能 $skill 显式调用，杜绝误触发
dependencies:
  tools:
    - type: "mcp"
      value: "sif-mcp"
      description: "SIF 数据 MCP"
```
- ✅ 动作：
- 易误触发的 Skill 对（如两个写作类或两个分析类 Skill）→ 给**次要**的设 `allow_implicit_invocation: false`，**从机制层根治触发打架**（比改描述更彻底）。
  - 依赖 MCP 的 Skill → 在此声明 `dependencies.tools`。

## 机制 ④ feature flag + 自动检测
- 需 `codex --enable skills` 开启。
- 改了自动检测；不生效就重启 Codex。
- 禁用某 Skill：编辑 `~/.codex/config.toml` 的 `[[skills.config]]`，设 `enabled = false`。
```toml
[[skills.config]]
path = "/path/to/skill/SKILL.md"
enabled = false
```

## 机制 ⑤ 内置工具链 + 官方评测 Cookbook
- `$skill-creator`：交互式创建/优化 Skill（方法 #20）。
- `$skill-installer`：安装 curated skills。
- 官方 Cookbook：Agent Improvement Loop with Traces, Evals, and Codex —— 方法 #12「Golden Set + Eval」的 Codex 官方实现路径。

---

## 方法论 → Codex 机制 映射表（速查）
| 方法 | 在 Codex 里怎么做 |
|------|-------------------|
| #1 分层加载 | SKILL.md 放骨架，references/ 放细节，渐进式披露自动生效 |
| #2 Few-shot | 范例放 references/examples.md，SKILL.md 链接过去 |
| #3 模板固化 | 模板放 assets/，指令要求复用而非重写 |
| #5 触发描述工程 | description 倒金字塔 + 触发词前置（应对截断） |
| #6 编排器 | 用 Subagents + Plugins 打包成编排单元 |
| #8 Schema 契约 | scripts/validate.py 做输入校验 |
| #10 脚本化计算 | 全放 scripts/，官方："Prefer scripts for deterministic behavior" |
| #12 Golden Set + Eval | 按官方 Agent Improvement Loop Cookbook 搭建 |
| #15 patch 沉淀 | SKILL.patch.md |
| #19 委派契约 | Codex Subagents，依赖在 openai.yaml 声明 |
| #20 skill-creator | 直接用内置 $skill-creator |
| 触发打架根治 | allow_implicit_invocation: false（Codex 独有，比改描述更彻底） |

---

## Codex 官方最佳实践（与本体系互相印证）
- "Keep each skill focused on one job" → MECE（模型 2）
- "Prefer instructions over scripts unless you need deterministic behavior" → 方法 #10 的边界
- "Write imperative steps with explicit inputs and outputs" → IPO 契约（模型 3）
- "Test prompts against the skill description to confirm trigger behavior" → 方法 #12 评测
- "Front-load the key use case and trigger words" → 机制 ① 的强制要求

---

## Codex Skill 目录规范（合规打包用）
```
my-skill/
├── SKILL.md            必需：YAML frontmatter(name+description) + 指令骨架
├── scripts/            可选：可执行代码（确定性计算）
├── references/         可选：细节文档（按需加载）
├── assets/             可选：模板、资源
└── agents/
    └── openai.yaml     可选：UI 元数据 + 触发策略 + 依赖声明
```

## 参考链接
- Codex Skills 官方文档：https://developers.openai.com/codex/skills
- Codex Subagents：https://developers.openai.com/codex/subagents
- Codex Plugins / Build：https://developers.openai.com/codex/plugins/build
- Agent Improvement Loop Cookbook：https://developers.openai.com/cookbook/examples/agents_sdk/agent_improvement_loop
- open agent skills 标准：https://agentskills.io/specification
- 官方 skills 示例库：https://github.com/openai/skills
