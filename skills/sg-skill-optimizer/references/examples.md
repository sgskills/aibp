# Few-shot：Skill 优化前后对比

> 仅在需要示例时读取。示例使用通用、虚构场景，不代表任何外部项目或业务资产。

## 范例 1：触发描述前置

### 优化前

```yaml
description: 这是一个功能丰富、适用范围广泛的分析助手……当用户上传客服工单并要求归类时使用。
```

问题：核心对象和动作埋在后半段，也没有反触发边界。

### 优化后

```yaml
description: Use when users need to classify customer-support tickets and extract urgency. Not for drafting replies or editing unrelated documents.
```

验收：第一句直接包含动作与对象；第二句排除相邻任务；总长不超过 1024 字符。

## 范例 2：把模糊判断改成决策分支

### 优化前

```text
根据情况选择详细或简短报告。
```

### 优化后

```text
IF 用户要求“展开/完整明细” → 输出 full。
ELIF 存在 FAIL 或安全红线 → 输出 standard，并保留全部红线。
ELSE → 输出 concise：结论、Top 3、下一步。
```

验收：同一输入重复执行时，输出档位选择一致。

## 范例 3：失败路径三段式

### 优化前

```text
运行检查脚本；失败时重试。
```

### 优化后

| 触发条件 | 首选处理 | 仍失败 |
|---|---|---|
| Python 命令不存在 | 使用当前 agent 已发现的 Python 运行时 | 转人工检查，标记未运行 |
| 输出不是合法 JSON | 保留退出码、stdout、stderr | 不采信分数，停止自动修改 |
| 目录只读 | 保持只读并报告权限 | 不绕过权限，不静默失败 |

验收：每类失败都有可观察证据和停止条件。

## 范例 4：书面案例升级为可执行回归

### 优化前

只有 `golden_set.md`，描述“应当识别坏 frontmatter”，没有输入文件或断言。

### 优化后

```text
tests/fixtures/04-bad-frontmatter/
├── case.json
└── target-skill/
    └── SKILL.md
```

`case.json` 声明预期 `blocked=true` 和 blocker 关键词；`scripts/run_eval.py` 执行后按断言决定退出码。

验收：失败案例会让 runner 返回非零；只有本轮全部通过才标记 `VERIFIED`。

## 范例 5：环境级扫描排除测试素材

### 优化前

递归查找所有 `SKILL.md`，把 `tests/fixtures/` 中的坏样本当成已安装 Skill，产生假冲突。

### 优化后

扫描时排除 `.git`、`tests`、`fixtures`、虚拟环境、依赖目录和缓存目录。

验收：对本 Skill 根目录审计时只发现根目录成品，不发现七个测试样本。
