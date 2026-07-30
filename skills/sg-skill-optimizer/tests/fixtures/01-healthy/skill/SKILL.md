---
name: healthy-reviewer
description: Use when reviewing structured product notes and producing a fixed quality report. Not for modifying source files or unrelated business decisions.
---

# Healthy Reviewer

## 输入输出契约

INPUT：用户提供的结构化笔记文本。  
OUTPUT：固定字段的只读诊断报告。

## 工作流

1. 校验输入；如果信息不足 → 提问一次，仍不足 → 标记未验证。
2. 按字段检查内容。
3. 输出格式固定为结论、证据、建议。
4. 验证全部字段后交付。

## 失败模式

| 触发条件 | 首选处理 | 仍失败 |
|---|---|---|
| 输入为空 | 请求用户补充 | 停止并标记未运行 |

🔴 CHECKPOINT · 🛑 STOP：本 Skill 只读，不修改、覆盖或删除原文件。

## 禁止事项

- 禁止编造缺失事实。
- 不得输出密钥、Token 或敏感数据。

## 资源索引

- 输出范例：`references/examples.md`
- 报告模板：`assets/diagnosis_report_template.md`
- 评测规格：`references/golden_set.md`
